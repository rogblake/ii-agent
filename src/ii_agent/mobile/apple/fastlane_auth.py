"""Apple authentication using fastlane's Spaceship library.

This module uses Ruby scripts with Spaceship to handle Apple authentication.
Spaceship properly manages SSL certificates and session handling, providing
reliable authentication with 2FA support via trusted devices.
"""

import asyncio
import json
import logging
import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

from .exceptions import (
    AppleAccountLockedError,
    AppleAuthenticationError,
    AppleBundleIdError,
    AppleCertificateError,
    AppleInvalidCredentialsError,
    AppleRateLimitError,
    AppleSessionExpiredError,
)
from .types import (
    AppleAuthState,
    AppleSession,
    AppleTeam,
    LoginResponse,
)

logger = logging.getLogger(__name__)

# Session validity duration
SESSION_DURATION_DAYS = 30

# Base directory for user-specific Spaceship sessions
# Each user gets their own subdirectory to prevent session conflicts
SPACESHIP_SESSIONS_BASE_DIR = "/tmp/spaceship_sessions"

# Ruby script template for fastlane authentication
# Uses Spaceship which handles Apple's auth properly
# This script handles both initial login (detecting 2FA) and login with 2FA code
FASTLANE_AUTH_SCRIPT = '''
require 'spaceship'
require 'json'
require 'fileutils'

def output_json(data)
  puts "---JSON_OUTPUT_START---"
  puts data.to_json
  puts "---JSON_OUTPUT_END---"
  exit(0)
end

# Flag to track if 2FA was requested
$twofa_requested = false
$twofa_code_to_use = nil

begin
  apple_id = ENV['APPLE_ID']
  password = ENV['APPLE_PASSWORD']
  two_fa_code = ENV['VERIFICATION_CODE']  # Optional - if provided, use it for 2FA
  cookie_path = ENV['SPACESHIP_COOKIE_PATH']  # User-specific session directory

  # Remove any problematic environment variables
  ENV.delete('SPACESHIP_2FA_SMS_DEFAULT_PHONE_NUMBER')

  # Set up user-specific cookie path if provided
  # This isolates sessions between different users on the server
  if cookie_path && !cookie_path.empty?
    FileUtils.mkdir_p(cookie_path) rescue nil
    Spaceship::Client.class_variable_set(:@@cookie_path, cookie_path) if Spaceship::Client.class_variable_defined?(:@@cookie_path)
  end

  # Only clear cached sessions if FORCE_FRESH_LOGIN is set
  # This clears only the user-specific session directory
  if ENV['FORCE_FRESH_LOGIN'] == '1'
    spaceship_dir = cookie_path || File.expand_path('~/.fastlane/spaceship')
    if File.directory?(spaceship_dir)
      Dir.glob(File.join(spaceship_dir, '*')).each do |f|
        FileUtils.rm_rf(f) rescue nil
      end
    end
  end

  # Store the code if provided
  $twofa_code_to_use = two_fa_code if two_fa_code && !two_fa_code.empty?

  # Monkey-patch Spaceship's 2FA code request method
  # This intercepts when Spaceship asks for a 2FA code
  module Spaceship
    class Client
      alias_method :original_ask_for_2fa_code, :ask_for_2fa_code if method_defined?(:ask_for_2fa_code)

      def ask_for_2fa_code(text)
        $twofa_requested = true
        if $twofa_code_to_use
          # Return the code we have
          return $twofa_code_to_use
        else
          # No code provided - output that 2FA is required and exit
          puts "---JSON_OUTPUT_START---"
          puts ({ 'success' => false, 'requires_2fa' => true, 'error' => '2fa_required', 'message' => 'Two-factor authentication required' }).to_json
          puts "---JSON_OUTPUT_END---"
          exit(0)
        end
      end
    end
  end

  # Also patch the portal client if it exists
  if defined?(Spaceship::Portal::Client)
    module Spaceship
      module Portal
        class Client
          def ask_for_2fa_code(text)
            $twofa_requested = true
            if $twofa_code_to_use
              return $twofa_code_to_use
            else
              puts "---JSON_OUTPUT_START---"
              puts ({ 'success' => false, 'requires_2fa' => true, 'error' => '2fa_required', 'message' => 'Two-factor authentication required' }).to_json
              puts "---JSON_OUTPUT_END---"
              exit(0)
            end
          end
        end
      end
    end
  end

  # Patch TunesClient as well
  if defined?(Spaceship::Tunes::TunesClient)
    module Spaceship
      module Tunes
        class TunesClient
          def ask_for_2fa_code(text)
            $twofa_requested = true
            if $twofa_code_to_use
              return $twofa_code_to_use
            else
              puts "---JSON_OUTPUT_START---"
              puts ({ 'success' => false, 'requires_2fa' => true, 'error' => '2fa_required', 'message' => 'Two-factor authentication required' }).to_json
              puts "---JSON_OUTPUT_END---"
              exit(0)
            end
          end
        end
      end
    end
  end

  # For Apple Developer accounts, 2FA is almost always required
  # Spaceship will attempt login and the patched method will handle 2FA
  begin
    # Use Tunes (App Store Connect) client which has better 2FA handling
    Spaceship::Tunes.login(apple_id, password)

    # If we get here, login succeeded (with or without 2FA)
    # IMPORTANT: Do NOT login to Portal here!
    # Portal.login() triggers a SEPARATE 2FA prompt (Apple treats Tunes and Portal as different apps).
    # We'll get Portal teams later during app setup when we actually need them.
    # For now, just get teams from Tunes - the team names are the same.
    teams = []

    # Skip Portal login entirely - it sends another OTP to the user
    if teams.empty?
      begin
        client = Spaceship::Tunes.client
        if client && client.respond_to?(:teams) && client.teams
          client.teams.each do |team|
            next unless team  # Skip nil teams

            # Handle different team structures - Spaceship may return different formats
            team_id = nil
            team_name = nil

            begin
              if team.is_a?(Hash)
                # Try different possible keys for team ID
                cp = team['contentProvider']
                if cp && cp.is_a?(Hash) && cp['contentProviderId']
                  team_id = cp['contentProviderId'].to_s
                  team_name = cp['name']
                elsif team['providerId']
                  team_id = team['providerId'].to_s
                  team_name = team['name']
                elsif team['teamId']
                  team_id = team['teamId'].to_s
                  team_name = team['name']
                elsif team['id']
                  team_id = team['id'].to_s
                  team_name = team['name']
                end
              end
            rescue => team_err
              # Skip this team if we can't parse it
              next
            end

            if team_id && !team_id.empty?
              teams << {
                'team_id' => team_id,
                'name' => team_name || 'Unknown Team',
                'team_type' => 'appstore'
              }
            end
          end
        end
      rescue => teams_err
        # If we can't get teams, return empty array
        teams = []
      end
    end

    output_json({
      'success' => true,
      'requires_2fa' => false,
      'teams' => teams
    })

  rescue Spaceship::Client::UnauthorizedAccessError => e
    # If we provided a 2FA code and still got unauthorized, the code was wrong
    if $twofa_code_to_use
      output_json({
        'success' => false,
        'error' => 'invalid_code',
        'message' => 'Invalid verification code'
      })
    else
      # No 2FA code provided - this means 2FA is required
      output_json({
        'success' => false,
        'requires_2fa' => true,
        'error' => '2fa_required',
        'message' => 'Two-factor authentication required'
      })
    end
  rescue Spaceship::Client::InvalidUserCredentialsError => e
    output_json({
      'success' => false,
      'error' => 'invalid_credentials',
      'message' => e.message
    })
  end

rescue Spaceship::Client::InvalidUserCredentialsError => e
  output_json({
    'success' => false,
    'error' => 'invalid_credentials',
    'message' => 'Invalid Apple ID or password'
  })
rescue Spaceship::Client::ProgramLicenseAgreementUpdated => e
  output_json({
    'success' => false,
    'error' => 'license_agreement',
    'message' => 'Please accept the updated Apple Developer Program License Agreement'
  })
rescue => e
  error_msg = e.message.to_s.downcase
  error_class = e.class.to_s

  # Check various indicators that 2FA is needed
  if error_msg.include?('two-factor') || error_msg.include?('two factor') ||
     error_msg.include?('2fa') || error_msg.include?('verification code') ||
     error_msg.include?('security code') || error_msg.include?('trusted device') ||
     error_msg.include?('phone number') || error_class.include?('TwoFactor')
    # If we provided a code and got a 2FA error, the code was wrong
    if $twofa_code_to_use
      output_json({
        'success' => false,
        'error' => 'invalid_code',
        'message' => 'Invalid verification code'
      })
    else
      output_json({
        'success' => false,
        'requires_2fa' => true,
        'error' => '2fa_required',
        'message' => 'Two-factor authentication required'
      })
    end
  elsif error_msg.include?('locked')
    output_json({
      'success' => false,
      'error' => 'account_locked',
      'message' => e.message
    })
  elsif error_msg.include?('rate') || error_msg.include?('too many')
    output_json({
      'success' => false,
      'error' => 'rate_limit',
      'message' => e.message
    })
  else
    output_json({
      'success' => false,
      'error' => 'unknown',
      'message' => "#{e.class}: #{e.message}"
    })
  end
end
'''

# FASTLANE_2FA_SCRIPT is no longer needed - FASTLANE_AUTH_SCRIPT handles both cases
# by checking if VERIFICATION_CODE is provided

FASTLANE_GET_TEAMS_SCRIPT = '''
require 'spaceship'
require 'json'

def output_json(data)
  puts "---JSON_OUTPUT_START---"
  puts data.to_json
  puts "---JSON_OUTPUT_END---"
  exit(0)
end

begin
  apple_id = ENV['APPLE_ID']
  password = ENV['APPLE_PASSWORD']
  cookie_path = ENV['SPACESHIP_COOKIE_PATH']

  # Set up user-specific cookie path if provided
  if cookie_path && !cookie_path.empty?
    FileUtils.mkdir_p(cookie_path) rescue nil
    Spaceship::Client.class_variable_set(:@@cookie_path, cookie_path) if Spaceship::Client.class_variable_defined?(:@@cookie_path)
  end

  # Login to get teams - should use cached session if available
  Spaceship::Tunes.login(apple_id, password)

  # Get teams from Portal (these have the correct team_id for Developer Portal operations)
  teams = []
  begin
    Spaceship::Portal.login(apple_id, password)
    portal_teams = Spaceship::Portal.client.teams || []
    portal_teams.each do |team|
      next unless team
      if team.is_a?(Hash)
        portal_team_id = team['teamId']
        portal_team_name = team['name']
        if portal_team_id && !portal_team_id.to_s.empty?
          teams << {
            'team_id' => portal_team_id.to_s,
            'name' => portal_team_name || 'Unknown Team',
            'team_type' => 'developer'
          }
        end
      end
    end
  rescue => portal_err
    # Portal login may fail, continue with Tunes teams
  end

  # If no Portal teams, try Tunes teams as fallback
  if teams.empty?
    begin
      client = Spaceship::Tunes.client
      if client && client.respond_to?(:teams) && client.teams
        client.teams.each do |team|
          next unless team

          team_id = nil
          team_name = nil

          begin
            if team.is_a?(Hash)
              cp = team['contentProvider']
              if cp && cp.is_a?(Hash) && cp['contentProviderId']
                team_id = cp['contentProviderId'].to_s
                team_name = cp['name']
              elsif team['providerId']
                team_id = team['providerId'].to_s
                team_name = team['name']
              elsif team['teamId']
                team_id = team['teamId'].to_s
                team_name = team['name']
              elsif team['id']
                team_id = team['id'].to_s
                team_name = team['name']
              end
            end
          rescue
            next
          end

          if team_id && !team_id.empty?
            teams << {
              'team_id' => team_id,
              'name' => team_name || 'Unknown Team',
              'team_type' => 'appstore'
            }
          end
        end
      end
    rescue
      teams = []
    end
  end

  output_json({
    'success' => true,
    'teams' => teams
  })

rescue => e
  output_json({
    'success' => false,
    'error' => 'session_expired',
    'message' => "#{e.class}: #{e.message}"
  })
end
'''

# Ruby script to create iOS Distribution Certificate using Spaceship
FASTLANE_CREATE_CERTIFICATE_SCRIPT = '''
require 'spaceship'
require 'json'
require 'openssl'
require 'fileutils'

def output_json(data)
  puts "---JSON_OUTPUT_START---"
  puts data.to_json
  puts "---JSON_OUTPUT_END---"
  exit(0)
end

# Store 2FA code if provided - this will be used if 2FA is triggered
$twofa_code_to_use = nil
two_fa_code = ENV['VERIFICATION_CODE']
$twofa_code_to_use = two_fa_code if two_fa_code && !two_fa_code.empty?

# Monkey-patch ALL client classes to handle 2FA with provided code
# This covers Tunes, Portal, and Connect API clients
module Spaceship
  class Client
    if method_defined?(:ask_for_2fa_code)
      alias_method :original_ask_for_2fa_code_cert, :ask_for_2fa_code
    end
    def ask_for_2fa_code(text)
      if $twofa_code_to_use
        return $twofa_code_to_use
      else
        output_json({
          'success' => false,
          'requires_2fa' => true,
          'error' => '2fa_required',
          'message' => 'Two-factor authentication required for certificate creation'
        })
      end
    end
  end
end

# Also patch PortalClient specifically
if defined?(Spaceship::PortalClient)
  class Spaceship::PortalClient
    def ask_for_2fa_code(text)
      if $twofa_code_to_use
        return $twofa_code_to_use
      else
        output_json({
          'success' => false,
          'requires_2fa' => true,
          'error' => '2fa_required',
          'message' => 'Two-factor authentication required for certificate creation'
        })
      end
    end
  end
end

begin
  apple_id = ENV['APPLE_ID']
  password = ENV['APPLE_PASSWORD']
  team_id = ENV['TEAM_ID']  # May be Tunes ID or Portal ID
  team_name = ENV['TEAM_NAME']  # Used to match Portal team if team_id doesn't work
  cookie_path = ENV['SPACESHIP_COOKIE_PATH']  # User-specific session directory

  # Set up user-specific cookie path if provided
  if cookie_path && !cookie_path.empty?
    FileUtils.mkdir_p(cookie_path) rescue nil
    Spaceship::Client.class_variable_set(:@@cookie_path, cookie_path) if Spaceship::Client.class_variable_defined?(:@@cookie_path)
  end

  # Use Spaceship::Portal directly for Developer Portal operations
  # The 2FA code will be used via the monkey-patched method if needed
  Spaceship::Portal.login(apple_id, password)

  # Get Portal teams and find the correct team ID
  # The team_id from Tunes (numeric) is different from Portal (alphanumeric)
  portal_team_id = team_id
  portal_teams = Spaceship::Portal.client.teams || []

  # Try to find matching team by team_id first, then by name
  matching_team = portal_teams.find { |t| t.is_a?(Hash) && t['teamId'].to_s == team_id.to_s }
  if !matching_team && team_name && !team_name.empty?
    matching_team = portal_teams.find { |t| t.is_a?(Hash) && t['name'] == team_name }
  end

  if matching_team
    portal_team_id = matching_team['teamId'].to_s
  elsif portal_teams.length == 1 && portal_teams[0].is_a?(Hash)
    # If only one team, use it
    portal_team_id = portal_teams[0]['teamId'].to_s
  end

  Spaceship::Portal.client.team_id = portal_team_id

  # Check existing distribution certificates
  existing_certs = Spaceship::Portal.certificate.production.all

  if existing_certs && !existing_certs.empty?
    # Check for valid (not expired) certificates
    valid_certs = existing_certs.select { |c| c.expires > Time.now }

    if valid_certs && !valid_certs.empty?
      cert = valid_certs.first
      output_json({
        'success' => true,
        'created' => false,
        'certificate_id' => cert.id,
        'name' => cert.name,
        'expiry' => cert.expires.to_s,
        'existing_count' => existing_certs.length,
        'message' => 'Using existing iOS Distribution Certificate'
      })
    end
  end

  # No valid certificate found, create a new one
  # Generate a new private key and CSR
  key = OpenSSL::PKey::RSA.new(2048)

  csr = OpenSSL::X509::Request.new
  csr.version = 0
  csr.subject = OpenSSL::X509::Name.new([
    ['CN', 'PEM', OpenSSL::ASN1::UTF8STRING],
    ['C', 'US', OpenSSL::ASN1::UTF8STRING]
  ])
  csr.public_key = key.public_key
  csr.sign(key, OpenSSL::Digest::SHA256.new)

  # Create certificate using CSR
  begin
    cert = Spaceship::Portal.certificate.production.create!(csr: csr)

    output_json({
      'success' => true,
      'created' => true,
      'certificate_id' => cert.id,
      'name' => cert.name,
      'expiry' => cert.expires.to_s,
      'existing_count' => (existing_certs || []).length,
      'message' => 'Created new iOS Distribution Certificate'
    })
  rescue Spaceship::Client::UnexpectedResponse => e
    if e.message.include?('maximum number') || e.message.include?('limit')
      output_json({
        'success' => false,
        'error' => 'max_certificates',
        'message' => 'Maximum number of certificates reached. Please revoke an existing certificate.',
        'existing_count' => (existing_certs || []).length
      })
    else
      raise e
    end
  end

rescue Spaceship::Client::UnauthorizedAccessError => e
  output_json({
    'success' => false,
    'error' => 'session_expired',
    'message' => 'Session expired. Please re-authenticate.'
  })
rescue Spaceship::Tunes::Error, Spaceship::Client::BasicPreferredInfoError => e
  # These errors typically indicate session/auth issues
  error_msg = e.message.to_s
  if error_msg.include?('hashcash') || error_msg.strip.empty?
    output_json({
      'success' => false,
      'error' => 'session_expired',
      'message' => 'Apple session expired or invalid. Please re-authenticate.'
    })
  else
    output_json({
      'success' => false,
      'error' => 'auth_error',
      'message' => "Authentication error: #{e.message}"
    })
  end
rescue => e
  error_msg = e.message.to_s
  # Check for common session expiration indicators
  if error_msg.include?('hashcash') || error_msg.include?('X-Apple-HC') ||
     e.class.to_s.include?('Tunes::Error')
    output_json({
      'success' => false,
      'error' => 'session_expired',
      'message' => 'Apple session expired. Please re-authenticate.'
    })
  else
    output_json({
      'success' => false,
      'error' => 'unknown',
      'message' => "#{e.class}: #{e.message}"
    })
  end
end
'''

# Ruby script to generate EAS credentials.json (certificate + provisioning profile)
# This creates everything needed for local EAS builds
FASTLANE_GENERATE_EAS_CREDENTIALS_SCRIPT = '''
require 'spaceship'
require 'json'
require 'openssl'
require 'fileutils'
require 'base64'

def output_json(data)
  puts "---JSON_OUTPUT_START---"
  puts data.to_json
  puts "---JSON_OUTPUT_END---"
  exit(0)
end

# Store 2FA code if provided
$twofa_code_to_use = nil
two_fa_code = ENV['VERIFICATION_CODE']
$twofa_code_to_use = two_fa_code if two_fa_code && !two_fa_code.empty?

# Monkey-patch for 2FA
module Spaceship
  class Client
    if method_defined?(:ask_for_2fa_code)
      alias_method :original_ask_for_2fa_code_eas, :ask_for_2fa_code
    end
    def ask_for_2fa_code(text)
      if $twofa_code_to_use
        return $twofa_code_to_use
      else
        output_json({
          'success' => false,
          'requires_2fa' => true,
          'error' => '2fa_required',
          'message' => 'Two-factor authentication required'
        })
      end
    end
  end
end

if defined?(Spaceship::PortalClient)
  class Spaceship::PortalClient
    def ask_for_2fa_code(text)
      if $twofa_code_to_use
        return $twofa_code_to_use
      else
        output_json({
          'success' => false,
          'requires_2fa' => true,
          'error' => '2fa_required',
          'message' => 'Two-factor authentication required'
        })
      end
    end
  end
end

begin
  apple_id = ENV['APPLE_ID']
  password = ENV['APPLE_PASSWORD']
  team_id = ENV['TEAM_ID']
  team_name = ENV['TEAM_NAME']
  bundle_identifier = ENV['BUNDLE_IDENTIFIER']
  cookie_path = ENV['SPACESHIP_COOKIE_PATH']

  # Set up user-specific cookie path
  if cookie_path && !cookie_path.empty?
    FileUtils.mkdir_p(cookie_path) rescue nil
    Spaceship::Client.class_variable_set(:@@cookie_path, cookie_path) if Spaceship::Client.class_variable_defined?(:@@cookie_path)
  end

  # Login to Portal
  Spaceship::Portal.login(apple_id, password)

  # Get Portal team ID
  portal_team_id = team_id
  portal_teams = Spaceship::Portal.client.teams || []

  matching_team = portal_teams.find { |t| t.is_a?(Hash) && t['teamId'].to_s == team_id.to_s }
  if !matching_team && team_name && !team_name.empty?
    matching_team = portal_teams.find { |t| t.is_a?(Hash) && t['name'] == team_name }
  end

  if matching_team
    portal_team_id = matching_team['teamId'].to_s
  elsif portal_teams.length == 1 && portal_teams[0].is_a?(Hash)
    portal_team_id = portal_teams[0]['teamId'].to_s
  end

  Spaceship::Portal.client.team_id = portal_team_id

  # Step 1: Always create a new distribution certificate with private key
  # We need the private key to create a valid P12 for signing
  # Existing certificates cannot be used because we don't have their private keys
  private_key = nil
  cert = nil
  cert_content = nil

  # Generate new private key and CSR
  private_key = OpenSSL::PKey::RSA.new(2048)

  csr = OpenSSL::X509::Request.new
  csr.version = 0
  csr.subject = OpenSSL::X509::Name.new([
    ['CN', 'EAS Build', OpenSSL::ASN1::UTF8STRING],
    ['C', 'US', OpenSSL::ASN1::UTF8STRING]
  ])
  csr.public_key = private_key.public_key
  csr.sign(private_key, OpenSSL::Digest::SHA256.new)

  # Use iOS Distribution certificate for App Store builds
  # Spaceship::Portal.certificate.production is actually for Distribution certificates
  begin
    cert = Spaceship::Portal.certificate.production.create!(csr: csr)
    cert_content = cert.download
  rescue Spaceship::Client::UnexpectedResponse => e
    if e.message.include?('maximum number') || e.message.include?('limit') || e.message.include?('You already have')
      # Maximum certificates reached - need to revoke one first
      # Try to revoke the oldest certificate and create a new one
      existing_certs = Spaceship::Portal.certificate.production.all || []
      valid_certs = existing_certs.select { |c| c.expires && c.expires.to_time > Time.now }

      if valid_certs && !valid_certs.empty?
        # Sort by expiry date (oldest first) and revoke the oldest
        oldest_cert = valid_certs.sort_by { |c| c.expires.to_time }.first
        begin
          oldest_cert.revoke!

          # Now try to create again with a fresh CSR
          private_key = OpenSSL::PKey::RSA.new(2048)
          csr = OpenSSL::X509::Request.new
          csr.version = 0
          csr.subject = OpenSSL::X509::Name.new([
            ['CN', 'EAS Build', OpenSSL::ASN1::UTF8STRING],
            ['C', 'US', OpenSSL::ASN1::UTF8STRING]
          ])
          csr.public_key = private_key.public_key
          csr.sign(private_key, OpenSSL::Digest::SHA256.new)

          cert = Spaceship::Portal.certificate.production.create!(csr: csr)
          cert_content = cert.download
        rescue => revoke_error
          output_json({
            'success' => false,
            'error' => 'max_certificates',
            'message' => "Maximum certificates reached and failed to auto-revoke. Please manually revoke a certificate in Apple Developer Portal. Error: #{revoke_error.message}"
          })
        end
      else
        output_json({
          'success' => false,
          'error' => 'max_certificates',
          'message' => 'Maximum certificates reached. Please revoke one in Apple Developer Portal.'
        })
      end
    else
      raise e
    end
  end

  # Validate certificate was created
  if cert.nil? || cert_content.nil?
    output_json({
      'success' => false,
      'error' => 'certificate_creation_failed',
      'message' => 'Failed to create or download distribution certificate'
    })
  end

  # Step 2: Get or create provisioning profile
  profile = nil
  profile_content = nil

  # Delete ALL existing App Store profiles for this bundle ID to start fresh
  all_profiles = Spaceship::Portal.provisioning_profile.app_store.all || []
  all_profiles.each do |p|
    if p.app && p.app.bundle_id == bundle_identifier
      begin
        p.delete!
      rescue => delete_error
        # Ignore delete errors
      end
    end
  end

  # Find the app/bundle ID
  app = Spaceship::Portal.app.find(bundle_identifier)

  if app.nil?
    output_json({
      'success' => false,
      'error' => 'bundle_id_not_found',
      'message' => "Bundle ID #{bundle_identifier} not found. Please register it first."
    })
  end

  # Create App Store provisioning profile with our certificate
  # Use an array with our single certificate
  profile_name = "EAS Build #{bundle_identifier} #{Time.now.to_i}"

  begin
    profile = Spaceship::Portal.provisioning_profile.app_store.create!(
      bundle_id: bundle_identifier,
      certificate: cert,
      name: profile_name
    )
    profile_content = profile.download
  rescue => e
    output_json({
      'success' => false,
      'error' => 'profile_creation_failed',
      'message' => "Failed to create provisioning profile: #{e.message}"
    })
  end

  # Verify the certificate in the profile matches our certificate
  # Get the fingerprint of our certificate
  our_cert_fingerprint = nil
  begin
    x509 = OpenSSL::X509::Certificate.new(cert_content)
    our_cert_fingerprint = OpenSSL::Digest::SHA1.hexdigest(x509.to_der).upcase
  rescue => e
    # Continue anyway
  end

  # Also get certificate IDs from the profile to verify it uses our certificate
  profile_cert_ids = profile.certificates.map { |c| c.id } rescue []
  our_cert_id = cert.id rescue nil

  if our_cert_id && !profile_cert_ids.include?(our_cert_id)
    # Profile doesn't include our certificate - this is a problem
    # Let's try to repair the profile with our certificate
    begin
      profile.repair!
      profile_content = profile.download
      # Re-check
      profile_cert_ids = profile.certificates.map { |c| c.id } rescue []
    rescue => repair_error
      # Continue anyway and let EAS Build fail with a more specific error
    end
  end

  # Build credentials.json structure for EAS
  # The private key is only available if we created a new certificate

  # Convert cert_content to PEM format if it's raw DER data
  cert_pem = nil
  if cert_content
    begin
      # cert_content from Spaceship is raw DER-encoded certificate
      if cert_content.is_a?(String)
        # Try to parse as DER and convert to PEM
        x509_cert = OpenSSL::X509::Certificate.new(cert_content)
        cert_pem = x509_cert.to_pem
      else
        cert_pem = cert_content.to_pem
      end
    rescue => e
      # If parsing fails, it might already be PEM or we'll skip it
      cert_pem = cert_content if cert_content.is_a?(String) && cert_content.include?('BEGIN CERTIFICATE')
    end
  end

  # Create P12 from certificate + private key (if we have private key)
  # Otherwise we can't create a valid P12 for signing
  p12_content = nil
  # Use a non-empty password - EAS Build doesn't handle empty passwords well
  p12_password = 'ii-agent-cert'

  if private_key && cert_content
    # We have both cert and private key - create P12
    begin
      x509_cert = OpenSSL::X509::Certificate.new(cert_content)

      # Verify the public key in the certificate matches our private key's public key
      cert_pub_key = x509_cert.public_key.to_pem
      our_pub_key = private_key.public_key.to_pem

      if cert_pub_key != our_pub_key
        output_json({
          'success' => false,
          'error' => 'key_mismatch',
          'message' => "Certificate public key doesn't match our private key. This means the certificate was not created with our CSR."
        })
      end

      # Create P12 using legacy algorithms for maximum macOS keychain compatibility
      # Use -legacy flag equivalent by specifying compatible algorithms
      # Write cert and key to temp files and use openssl command line for better compatibility
      require 'tempfile'

      cert_file = Tempfile.new(['cert', '.pem'])
      key_file = Tempfile.new(['key', '.pem'])
      p12_file = Tempfile.new(['output', '.p12'])

      begin
        cert_file.write(x509_cert.to_pem)
        cert_file.close
        key_file.write(private_key.to_pem)
        key_file.close
        p12_file.close

        # Use openssl command with legacy provider for maximum compatibility
        # The -legacy flag ensures compatibility with older macOS keychain versions
        cmd = "openssl pkcs12 -export -in #{cert_file.path} -inkey #{key_file.path} -out #{p12_file.path} -passout pass:#{p12_password} -legacy 2>&1"
        result = `#{cmd}`
        exit_code = $?.exitstatus

        if exit_code != 0
          # Try without -legacy flag (older openssl versions)
          cmd = "openssl pkcs12 -export -in #{cert_file.path} -inkey #{key_file.path} -out #{p12_file.path} -passout pass:#{p12_password} 2>&1"
          result = `#{cmd}`
          exit_code = $?.exitstatus
        end

        if exit_code != 0
          output_json({
            'success' => false,
            'error' => 'p12_creation_failed',
            'message' => "OpenSSL P12 creation failed: #{result}"
          })
        end

        p12_content = File.binread(p12_file.path)
      ensure
        cert_file.unlink
        key_file.unlink
        p12_file.unlink
      end
    rescue => e
      output_json({
        'success' => false,
        'error' => 'p12_creation_failed',
        'message' => "Failed to create P12: #{e.message}"
      })
    end
  elsif cert_content && !private_key
    # We have cert but no private key - this won't work for signing
    # EAS requires a P12 with private key
    output_json({
      'success' => false,
      'error' => 'no_private_key',
      'message' => 'Cannot create P12 without private key. You have an existing certificate but we cannot access its private key. Please revoke it in Apple Developer Portal and try again to create a new one.'
    })
  end

  # Validate we have all required data before outputting success
  if p12_content.nil?
    output_json({
      'success' => false,
      'error' => 'missing_p12',
      'message' => "P12 content is nil. cert_content=#{cert_content.nil? ? 'nil' : 'present'}, private_key=#{private_key.nil? ? 'nil' : 'present'}"
    })
  end

  if profile_content.nil?
    output_json({
      'success' => false,
      'error' => 'missing_profile',
      'message' => 'Provisioning profile content is nil'
    })
  end

  # Calculate certificate fingerprint from the original certificate
  # (We can't verify the P12 with Ruby because legacy format uses RC2 which Ruby doesn't support)
  p12_cert_fingerprint = nil
  begin
    x509 = OpenSSL::X509::Certificate.new(cert_content)
    p12_cert_fingerprint = OpenSSL::Digest::SHA1.hexdigest(x509.to_der).upcase
  rescue => e
    # Continue anyway - fingerprint is just for logging
    p12_cert_fingerprint = 'unknown'
  end

  # Output the raw credentials for the handler to write as files
  output_json({
    'success' => true,
    'p12_base64' => Base64.strict_encode64(p12_content),
    'p12_password' => p12_password,
    'provisioning_profile_base64' => Base64.strict_encode64(profile_content.to_s),
    'certificate_id' => cert ? cert.id : nil,
    'certificate_name' => cert ? cert.name : nil,
    'certificate_expiry' => cert ? cert.expires.to_s : nil,
    'certificate_fingerprint' => p12_cert_fingerprint,
    'profile_id' => profile ? profile.id : nil,
    'profile_name' => profile ? profile.name : nil,
    'profile_expiry' => profile ? profile.expires.to_s : nil,
    'profile_certificate_ids' => profile_cert_ids,
    'our_certificate_id' => our_cert_id,
    'has_private_key' => !private_key.nil?,
    'message' => "Created credentials. Cert fingerprint: #{p12_cert_fingerprint}, Cert ID: #{our_cert_id}, Profile cert IDs: #{profile_cert_ids.join(',')}"
  })

rescue Spaceship::Client::UnauthorizedAccessError => e
  output_json({
    'success' => false,
    'error' => 'session_expired',
    'message' => 'Session expired. Please re-authenticate.'
  })
rescue => e
  error_msg = e.message.to_s
  if error_msg.include?('hashcash') || error_msg.include?('X-Apple-HC')
    output_json({
      'success' => false,
      'error' => 'session_expired',
      'message' => 'Apple session expired. Please re-authenticate.'
    })
  else
    output_json({
      'success' => false,
      'error' => 'unknown',
      'message' => "#{e.class}: #{e.message}"
    })
  end
end
'''

# Ruby script to register Bundle ID using Spaceship
FASTLANE_REGISTER_BUNDLE_ID_SCRIPT = '''
require 'spaceship'
require 'json'
require 'fileutils'

def output_json(data)
  puts "---JSON_OUTPUT_START---"
  puts data.to_json
  puts "---JSON_OUTPUT_END---"
  exit(0)
end

# Store 2FA code if provided - this will be used if 2FA is triggered
$twofa_code_to_use = nil
two_fa_code = ENV['VERIFICATION_CODE']
$twofa_code_to_use = two_fa_code if two_fa_code && !two_fa_code.empty?

# Monkey-patch ALL client classes to handle 2FA with provided code
# This covers Tunes, Portal, and Connect API clients
module Spaceship
  class Client
    if method_defined?(:ask_for_2fa_code)
      alias_method :original_ask_for_2fa_code_bundle, :ask_for_2fa_code
    end
    def ask_for_2fa_code(text)
      if $twofa_code_to_use
        return $twofa_code_to_use
      else
        output_json({
          'success' => false,
          'requires_2fa' => true,
          'error' => '2fa_required',
          'message' => 'Two-factor authentication required for bundle ID registration'
        })
      end
    end
  end
end

# Also patch PortalClient specifically
if defined?(Spaceship::PortalClient)
  class Spaceship::PortalClient
    def ask_for_2fa_code(text)
      if $twofa_code_to_use
        return $twofa_code_to_use
      else
        output_json({
          'success' => false,
          'requires_2fa' => true,
          'error' => '2fa_required',
          'message' => 'Two-factor authentication required for bundle ID registration'
        })
      end
    end
  end
end

begin
  apple_id = ENV['APPLE_ID']
  password = ENV['APPLE_PASSWORD']
  team_id = ENV['TEAM_ID']  # May be Tunes ID or Portal ID
  team_name = ENV['TEAM_NAME']  # Used to match Portal team if team_id doesn't work
  bundle_identifier = ENV['BUNDLE_IDENTIFIER']
  app_name = ENV['APP_NAME']
  cookie_path = ENV['SPACESHIP_COOKIE_PATH']  # User-specific session directory

  # Set up user-specific cookie path if provided
  if cookie_path && !cookie_path.empty?
    FileUtils.mkdir_p(cookie_path) rescue nil
    Spaceship::Client.class_variable_set(:@@cookie_path, cookie_path) if Spaceship::Client.class_variable_defined?(:@@cookie_path)
  end

  # Use Spaceship::Portal directly for Developer Portal operations
  # The 2FA code will be used via the monkey-patched method if needed
  Spaceship::Portal.login(apple_id, password)

  # Get Portal teams and find the correct team ID
  # The team_id from Tunes (numeric) is different from Portal (alphanumeric)
  portal_team_id = team_id
  portal_teams = Spaceship::Portal.client.teams || []

  # Try to find matching team by team_id first, then by name
  matching_team = portal_teams.find { |t| t.is_a?(Hash) && t['teamId'].to_s == team_id.to_s }
  if !matching_team && team_name && !team_name.empty?
    matching_team = portal_teams.find { |t| t.is_a?(Hash) && t['name'] == team_name }
  end

  if matching_team
    portal_team_id = matching_team['teamId'].to_s
  elsif portal_teams.length == 1 && portal_teams[0].is_a?(Hash)
    # If only one team, use it
    portal_team_id = portal_teams[0]['teamId'].to_s
  end

  Spaceship::Portal.client.team_id = portal_team_id

  # Check if bundle ID already exists
  existing = Spaceship::Portal.app.find(bundle_identifier)

  if existing
    output_json({
      'success' => true,
      'created' => false,
      'bundle_id' => existing.bundle_id,
      'name' => existing.name,
      'message' => 'Bundle ID already exists'
    })
  end

  # Create new bundle ID
  begin
    app = Spaceship::Portal.app.create!(
      bundle_id: bundle_identifier,
      name: app_name,
      enable_services: {}
    )

    output_json({
      'success' => true,
      'created' => true,
      'bundle_id' => app.bundle_id,
      'name' => app.name,
      'message' => 'Bundle ID registered successfully'
    })
  rescue Spaceship::Client::UnexpectedResponse => e
    if e.message.include?('already exists') || e.message.include?('already taken')
      output_json({
        'success' => false,
        'error' => 'already_exists',
        'message' => 'Bundle ID already exists'
      })
    else
      raise e
    end
  end

rescue Spaceship::Client::UnauthorizedAccessError => e
  output_json({
    'success' => false,
    'error' => 'session_expired',
    'message' => 'Session expired. Please re-authenticate.'
  })
rescue Spaceship::Tunes::Error, Spaceship::Client::BasicPreferredInfoError => e
  # These errors typically indicate session/auth issues
  error_msg = e.message.to_s
  if error_msg.include?('hashcash') || error_msg.strip.empty?
    output_json({
      'success' => false,
      'error' => 'session_expired',
      'message' => 'Apple session expired or invalid. Please re-authenticate.'
    })
  else
    output_json({
      'success' => false,
      'error' => 'auth_error',
      'message' => "Authentication error: #{e.message}"
    })
  end
rescue => e
  error_msg = e.message.to_s
  # Check for common session expiration indicators
  if error_msg.include?('hashcash') || error_msg.include?('X-Apple-HC') ||
     e.class.to_s.include?('Tunes::Error')
    output_json({
      'success' => false,
      'error' => 'session_expired',
      'message' => 'Apple session expired. Please re-authenticate.'
    })
  else
    output_json({
      'success' => false,
      'error' => 'unknown',
      'message' => "#{e.class}: #{e.message}"
    })
  end
end
'''

# Ruby script to create App in App Store Connect using Spaceship ConnectAPI
# Based on fastlane documentation: https://github.com/fastlane/fastlane/blob/master/spaceship/docs/AppStoreConnect.md
# App.create accepts bundle_id as a STRING (not BundleId object ID)
FASTLANE_CREATE_APP_SCRIPT = '''
require 'spaceship'
require 'json'
require 'fileutils'

def output_json(data)
  puts "---JSON_OUTPUT_START---"
  puts data.to_json
  puts "---JSON_OUTPUT_END---"
  exit(0)
end

# Store 2FA code if provided
$twofa_code_to_use = nil
two_fa_code = ENV['VERIFICATION_CODE']
$twofa_code_to_use = two_fa_code if two_fa_code && !two_fa_code.empty?

# Monkey-patch to handle 2FA
module Spaceship
  class Client
    if method_defined?(:ask_for_2fa_code)
      alias_method :original_ask_for_2fa_code_app, :ask_for_2fa_code
    end
    def ask_for_2fa_code(text)
      if $twofa_code_to_use
        return $twofa_code_to_use
      else
        output_json({
          'success' => false,
          'requires_2fa' => true,
          'error' => '2fa_required',
          'message' => 'Two-factor authentication required for app creation'
        })
      end
    end
  end
end

begin
  apple_id = ENV['APPLE_ID']
  password = ENV['APPLE_PASSWORD']
  team_id = ENV['TEAM_ID']
  team_name = ENV['TEAM_NAME']
  bundle_identifier = ENV['BUNDLE_IDENTIFIER']
  app_name = ENV['APP_NAME']
  sku = ENV['SKU'] || bundle_identifier.gsub('.', '_')
  cookie_path = ENV['SPACESHIP_COOKIE_PATH']

  # Set up user-specific cookie path if provided
  if cookie_path && !cookie_path.empty?
    FileUtils.mkdir_p(cookie_path) rescue nil
    Spaceship::Client.class_variable_set(:@@cookie_path, cookie_path) if Spaceship::Client.class_variable_defined?(:@@cookie_path)
  end

  # Set team NAME for App Store Connect (Tunes) - must be set BEFORE login
  ENV['FASTLANE_ITC_TEAM_NAME'] = team_name if team_name && !team_name.empty?

  # IMPORTANT: Do NOT call Portal.login before ConnectAPI.login
  # It causes client state conflicts resulting in "undefined method for nil"
  # Use ConnectAPI.login with use_portal: false, use_tunes: true
  # App creation only needs Tunes (App Store Connect), not Portal
  Spaceship::ConnectAPI.login(apple_id, password, use_portal: false, use_tunes: true)

  # Check if app already exists using App.find (more reliable than App.all)
  existing_app = nil
  begin
    existing_app = Spaceship::ConnectAPI::App.find(bundle_identifier)
  rescue => find_err
    # App not found or error - continue to create
    STDERR.puts "App.find result: #{find_err.message}" if find_err
  end

  if existing_app
    output_json({
      'success' => true,
      'created' => false,
      'app_id' => existing_app.id,
      'bundle_id' => existing_app.bundle_id,
      'name' => existing_app.name,
      'message' => 'App already exists in App Store Connect'
    })
  end

  # Create the app using ConnectAPI
  # Per fastlane docs, bundle_id is a STRING (the identifier like "com.example.app")
  # NOT a BundleId object ID
  begin
    response = Spaceship::ConnectAPI::App.create(
      name: app_name,
      version_string: '1.0.0',
      sku: sku,
      primary_locale: 'en-US',
      bundle_id: bundle_identifier,  # String identifier, not BundleId object
      platforms: ['IOS'],
      company_name: team_name || 'Company'
    )

    # App.create returns a Response object, not an App directly
    # Extract the app from the response
    new_app = nil
    if response.is_a?(Spaceship::ConnectAPI::Response)
      new_app = response.to_a.first
    elsif response.is_a?(Spaceship::ConnectAPI::App)
      new_app = response
    else
      # If we can't get the app from response, try to find it
      new_app = Spaceship::ConnectAPI::App.find(bundle_identifier)
    end

    if new_app
      output_json({
        'success' => true,
        'created' => true,
        'app_id' => new_app.id,
        'bundle_id' => new_app.bundle_id,
        'name' => new_app.name,
        'message' => 'App created in App Store Connect'
      })
    else
      # App was created but we couldn't retrieve it - still a success
      output_json({
        'success' => true,
        'created' => true,
        'app_id' => nil,
        'bundle_id' => bundle_identifier,
        'name' => app_name,
        'message' => 'App created in App Store Connect (details unavailable)'
      })
    end
  rescue StandardError => e
    error_msg = e.message.to_s.downcase
    full_error_msg = e.message.to_s

    if error_msg.include?('already exists') || error_msg.include?('already taken') || error_msg.include?('duplicate') || error_msg.include?('has already been taken') || error_msg.include?('already been used')
      # Try to find an existing app with this bundle ID in our account
      existing_app_in_account = nil
      begin
        existing_app_in_account = Spaceship::ConnectAPI::App.find(bundle_identifier)
      rescue
        # Not found in our account
      end

      if existing_app_in_account
        # We actually have this app - return success
        output_json({
          'success' => true,
          'created' => false,
          'app_id' => existing_app_in_account.id,
          'bundle_id' => existing_app_in_account.bundle_id,
          'name' => existing_app_in_account.name,
          'message' => 'App already exists in App Store Connect'
        })
      end

      # App not found in our account - determine if it's a name or bundle ID conflict
      # Apple returns different messages for name vs bundle ID conflicts:
      # - "The App Name you entered has already been used" = name conflict (global)
      # - "An App ID with Identifier X is not available" = bundle ID conflict
      # - "has already been taken" with "name" context = name conflict
      # Check for bundle ID conflict first (more specific)
      is_bundle_conflict = error_msg.include?('identifier') || error_msg.include?('bundle id') || error_msg.include?('app id')
      # Name conflict - only if it specifically mentions "app name" or "name" with "taken/used"
      is_name_conflict = error_msg.include?('app name') || error_msg.include?('name you entered') || (error_msg.include?('name') && (error_msg.include?('taken') || error_msg.include?('used')))

      if is_name_conflict && !is_bundle_conflict
        output_json({
          'success' => false,
          'error' => 'name_taken',
          'conflict_type' => 'name',
          'message' => "The app name '#{app_name}' is already taken on the App Store. Please choose a different name.",
          'original_error' => full_error_msg
        })
      elsif is_bundle_conflict && !is_name_conflict
        output_json({
          'success' => false,
          'error' => 'bundle_id_taken',
          'conflict_type' => 'bundle_id',
          'message' => "The bundle ID '#{bundle_identifier}' is already registered by another developer. Please use a different bundle ID.",
          'original_error' => full_error_msg
        })
      else
        # Generic already exists - could be either
        output_json({
          'success' => false,
          'error' => 'already_exists',
          'conflict_type' => 'unknown',
          'message' => 'An app with this bundle ID or name already exists. Try a different app name or bundle ID.',
          'original_error' => full_error_msg
        })
      end
    else
      raise e
    end
  end

rescue Spaceship::Client::UnauthorizedAccessError => e
  output_json({
    'success' => false,
    'error' => 'session_expired',
    'message' => 'Session expired. Please re-authenticate.'
  })
rescue StandardError => e
  # Check for access forbidden
  if e.class.to_s.include?('Forbidden') || e.message.to_s.include?('forbidden')
    output_json({
      'success' => false,
      'error' => 'session_expired',
      'message' => 'Session expired. Please re-authenticate.'
    })
  else
    output_json({
      'success' => false,
      'error' => 'unknown',
      'message' => "#{e.class}: #{e.message}"
    })
  end
end
'''

# Ruby script to list existing apps from App Store Connect using ConnectAPI
FASTLANE_LIST_APPS_SCRIPT = '''
require 'spaceship'
require 'json'
require 'fileutils'

def output_json(data)
  puts "---JSON_OUTPUT_START---"
  puts data.to_json
  puts "---JSON_OUTPUT_END---"
  exit(0)
end

# Store 2FA code if provided
$twofa_code_to_use = nil
two_fa_code = ENV['VERIFICATION_CODE']
$twofa_code_to_use = two_fa_code if two_fa_code && !two_fa_code.empty?

# Monkey-patch to handle 2FA
module Spaceship
  class Client
    if method_defined?(:ask_for_2fa_code)
      alias_method :original_ask_for_2fa_code_list, :ask_for_2fa_code
    end
    def ask_for_2fa_code(text)
      if $twofa_code_to_use
        return $twofa_code_to_use
      else
        output_json({
          'success' => false,
          'requires_2fa' => true,
          'error' => '2fa_required',
          'message' => 'Two-factor authentication required'
        })
      end
    end
  end
end

begin
  apple_id = ENV['APPLE_ID']
  password = ENV['APPLE_PASSWORD']
  team_id = ENV['TEAM_ID']
  team_name = ENV['TEAM_NAME']
  cookie_path = ENV['SPACESHIP_COOKIE_PATH']

  # Set up user-specific cookie path if provided
  if cookie_path && !cookie_path.empty?
    FileUtils.mkdir_p(cookie_path) rescue nil
    Spaceship::Client.class_variable_set(:@@cookie_path, cookie_path) if Spaceship::Client.class_variable_defined?(:@@cookie_path)
  end

  # IMPORTANT: Set team ID/name environment variables BEFORE login
  # Spaceship checks these during login to auto-select the team
  ENV['FASTLANE_ITC_TEAM_ID'] = team_id if team_id && !team_id.empty?
  ENV['FASTLANE_ITC_TEAM_NAME'] = team_name if team_name && !team_name.empty?

  # Login using ConnectAPI (modern App Store Connect API)
  Spaceship::ConnectAPI.login(apple_id, password, use_portal: false, use_tunes: true)

  # Get all apps using ConnectAPI
  apps = Spaceship::ConnectAPI::App.all
  app_list = []

  require 'net/http'
  require 'uri'

  apps.each do |app|
    app_data = {
      'app_id' => app.id,
      'bundle_id' => app.bundle_id,
      'name' => app.name,
      'sku' => app.sku,
      'icon_url' => nil
    }

    # Try multiple methods to get app icon
    icon_url = nil

    # Method 1: Try to get icon from App Store Connect API (app info/localization)
    begin
      # Fetch app infos which contain icons
      app_infos = app.get_app_infos
      if app_infos && !app_infos.empty?
        app_info = app_infos.first
        # Try to get localizations which may have app icon
        if app_info.respond_to?(:get_app_info_localizations)
          localizations = app_info.get_app_info_localizations
          if localizations && !localizations.empty?
            loc = localizations.first
            # Check for app icon in localization
            if loc.respond_to?(:app_icon) && loc.app_icon
              icon_url = loc.app_icon.url rescue nil
            end
          end
        end
      end
    rescue => asc_err
      STDERR.puts "ASC icon fetch failed for #{app.bundle_id}: #{asc_err.message}"
    end

    # Method 2: Try iTunes Lookup API (works for published apps)
    if icon_url.nil?
      begin
        lookup_url = URI.parse("https://itunes.apple.com/lookup?bundleId=#{app.bundle_id}&country=US")
        http = Net::HTTP.new(lookup_url.host, lookup_url.port)
        http.use_ssl = true
        http.open_timeout = 5
        http.read_timeout = 5
        request = Net::HTTP::Get.new(lookup_url)
        response = http.request(request)

        if response.code == '200'
          lookup_data = JSON.parse(response.body)
          if lookup_data['resultCount'] && lookup_data['resultCount'] > 0
            result = lookup_data['results'][0]
            # Get the highest resolution icon available
            icon_url = result['artworkUrl512'] || result['artworkUrl100'] || result['artworkUrl60']
          end
        end
      rescue => icon_err
        STDERR.puts "iTunes icon fetch failed for #{app.bundle_id}: #{icon_err.message}"
      end
    end

    app_data['icon_url'] = icon_url
    app_list << app_data
  end

  output_json({
    'success' => true,
    'apps' => app_list
  })

rescue Spaceship::Client::UnauthorizedAccessError, Spaceship::AccessForbiddenError => e
  output_json({
    'success' => false,
    'error' => 'session_expired',
    'message' => 'Session expired. Please re-authenticate.'
  })
rescue => e
  output_json({
    'success' => false,
    'error' => 'unknown',
    'message' => "#{e.class}: #{e.message}"
  })
end
'''


class FastlaneAuthClient:
    """Apple authentication client using fastlane's Spaceship library.

    This provides reliable authentication by leveraging Spaceship's
    battle-tested Apple API integration with proper SSL handling.
    """

    def __init__(self):
        self._check_fastlane_installed()

    def _get_user_cookie_path(self, user_id: str) -> str:
        """Get the user-specific Spaceship cookie/session path.

        Each user gets their own directory to prevent session conflicts
        when multiple users authenticate simultaneously.

        Args:
            user_id: The user's unique identifier

        Returns:
            Path to the user's Spaceship session directory
        """
        # Sanitize user_id to be filesystem-safe
        safe_user_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in user_id)
        user_path = os.path.join(SPACESHIP_SESSIONS_BASE_DIR, safe_user_id)

        # Ensure the directory exists
        os.makedirs(user_path, exist_ok=True)

        return user_path

    def _check_fastlane_installed(self) -> bool:
        """Check if fastlane is installed."""
        try:
            result = subprocess.run(
                ['fastlane', '--version'],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("Fastlane not installed")
            return False

    def _run_ruby_script(
        self,
        script: str,
        env: dict[str, str],
        timeout: int = 60
    ) -> dict[str, Any]:
        """Run a Ruby script and parse JSON output."""
        # Create a temporary file for the script
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.rb',
            delete=False
        ) as f:
            f.write(script)
            script_path = f.name

        try:
            # Build environment
            run_env = os.environ.copy()
            run_env.update(env)

            # Run the script
            result = subprocess.run(
                ['ruby', script_path],
                env=run_env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            # Log raw output for debugging
            logger.info(f"Ruby script stdout: {result.stdout[:500] if result.stdout else 'empty'}")
            if result.stderr:
                logger.info(f"Ruby script stderr: {result.stderr[:500]}")

            # Parse JSON output
            output = result.stdout
            if '---JSON_OUTPUT_START---' in output:
                json_start = output.find('---JSON_OUTPUT_START---') + len('---JSON_OUTPUT_START---')
                json_end = output.find('---JSON_OUTPUT_END---')
                json_str = output[json_start:json_end].strip()
                parsed = json.loads(json_str)
                logger.info(f"Parsed Ruby output: {parsed}")
                return parsed
            else:
                # Check stderr for errors
                logger.error(f"Ruby script failed - no JSON output. stdout: {result.stdout}, stderr: {result.stderr}")

                # Check if stderr contains 2FA-related messages
                stderr_lower = (result.stderr or '').lower()
                if 'two-factor' in stderr_lower or '2fa' in stderr_lower or 'verification' in stderr_lower:
                    return {
                        'success': False,
                        'requires_2fa': True,
                        'error': '2fa_required',
                        'message': 'Two-factor authentication required'
                    }

                return {
                    'success': False,
                    'error': 'script_error',
                    'message': result.stderr or 'Unknown error'
                }

        except subprocess.TimeoutExpired:
            logger.error("Ruby script timed out")
            return {
                'success': False,
                'error': 'timeout',
                'message': 'Authentication timed out'
            }
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON output: {e}")
            return {
                'success': False,
                'error': 'parse_error',
                'message': str(e)
            }
        finally:
            # Clean up temp file
            try:
                os.unlink(script_path)
            except Exception:
                pass

    async def initiate_login(
        self, apple_id: str, password: str, user_id: str
    ) -> LoginResponse:
        """Initiate Apple ID login using fastlane.

        Args:
            apple_id: Apple ID email
            password: Apple ID password
            user_id: The user's unique identifier (for session isolation)

        Returns:
            LoginResponse with session and 2FA requirement flag
        """
        # Get user-specific cookie path for session isolation
        cookie_path = self._get_user_cookie_path(user_id)

        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self._run_ruby_script,
            FASTLANE_AUTH_SCRIPT,
            {
                'APPLE_ID': apple_id,
                'APPLE_PASSWORD': password,
                'FASTLANE_DONT_STORE_PASSWORD': '1',
                'FASTLANE_SKIP_UPDATE_CHECK': '1',
                'FORCE_FRESH_LOGIN': '1',  # Clear cache for initial login
                'SPACESHIP_COOKIE_PATH': cookie_path,  # User-specific session
            },
            120,  # 2 minute timeout for login
        )

        # Log the result for debugging
        logger.info(f"Fastlane auth result: success={result.get('success')}, "
                   f"requires_2fa={result.get('requires_2fa')}, "
                   f"error={result.get('error')}")

        if result.get('success'):
            # Login succeeded
            session = AppleSession(
                session_id=str(uuid.uuid4()),
                scnt='',
                x_apple_id_session_id=result.get('session_id', ''),
                auth_state=AppleAuthState.PENDING_TEAM_SELECTION,
                apple_id=apple_id,
                cookies=result.get('cookies', {}),
                teams=[
                    AppleTeam(
                        team_id=t['team_id'],
                        name=t['name'],
                        team_type=t['team_type'],
                    )
                    for t in result.get('teams', [])
                ],
                expiry=datetime.now(timezone.utc) + timedelta(days=SESSION_DURATION_DAYS),
            )
            return LoginResponse(
                session=session,
                requires_2fa=False,
                auth_type=None,
            )

        elif result.get('requires_2fa') or result.get('error') == '2fa_required':
            # 2FA required - store the session tokens for verification
            session = AppleSession(
                session_id=str(uuid.uuid4()),
                scnt=result.get('scnt', ''),
                x_apple_id_session_id=result.get('session_id', ''),
                auth_state=AppleAuthState.PENDING_2FA,
                apple_id=apple_id,
                cookies={},
                expiry=datetime.now(timezone.utc) + timedelta(days=SESSION_DURATION_DAYS),
            )
            # Store password temporarily for 2FA step (will be cleared after)
            session._temp_password = password
            return LoginResponse(
                session=session,
                requires_2fa=True,
                auth_type=result.get('auth_type', 'hsa2'),
            )

        else:
            # Handle errors
            error = result.get('error', 'unknown')
            message = result.get('message', 'Authentication failed')

            if error == 'invalid_credentials':
                raise AppleInvalidCredentialsError()
            elif error == 'account_locked':
                raise AppleAccountLockedError()
            elif error == 'rate_limit':
                raise AppleRateLimitError()
            else:
                raise AppleAuthenticationError(message)

    async def verify_2fa_code(
        self,
        session: AppleSession,
        code: str,
        password: str,
        user_id: str,
    ) -> AppleSession:
        """Verify 2FA code using Spaceship.

        This re-runs the full login with the 2FA code provided. Spaceship will
        use the monkey-patched ask_for_2fa_code method to get the code.

        Args:
            session: Current session from login
            code: 6-digit verification code
            password: Apple ID password (needed for Spaceship re-login with 2FA)
            user_id: The user's unique identifier (for session isolation)

        Returns:
            Updated session with authenticated state
        """
        # Get user-specific cookie path for session isolation
        cookie_path = self._get_user_cookie_path(user_id)

        loop = asyncio.get_event_loop()
        # Use the same auth script but with VERIFICATION_CODE set
        # The script will monkey-patch Spaceship to use this code
        result = await loop.run_in_executor(
            None,
            self._run_ruby_script,
            FASTLANE_AUTH_SCRIPT,
            {
                'APPLE_ID': session.apple_id,
                'APPLE_PASSWORD': password,
                'VERIFICATION_CODE': code,
                'FASTLANE_DONT_STORE_PASSWORD': '1',
                'FASTLANE_SKIP_UPDATE_CHECK': '1',
                'SPACESHIP_COOKIE_PATH': cookie_path,  # User-specific session
            },
            120,
        )

        logger.info(f"2FA verification result: {result}")

        if result.get('success'):
            # Update session with teams from successful login
            session.auth_state = AppleAuthState.PENDING_TEAM_SELECTION
            session.teams = [
                AppleTeam(
                    team_id=t['team_id'],
                    name=t['name'],
                    team_type=t['team_type'],
                )
                for t in result.get('teams', [])
            ]
            return session
        else:
            error = result.get('error', 'unknown')
            message = result.get('message', 'Verification failed')

            if error == 'invalid_code':
                from .exceptions import Apple2FAInvalidCodeError
                raise Apple2FAInvalidCodeError()
            else:
                raise AppleAuthenticationError(message)

    async def get_teams(self, session: AppleSession) -> list[AppleTeam]:
        """Get available teams from session.

        If teams are already in session, return them.
        """
        if session.teams:
            return session.teams

        # Teams should have been populated during 2FA verification
        # Return empty list if not available
        return []

        return []

    async def select_team(self, session: AppleSession, team_id: str) -> AppleSession:
        """Select a team for subsequent operations."""
        team = next((t for t in session.teams if t.team_id == team_id), None)
        if not team:
            raise AppleAuthenticationError(f"Team {team_id} not found")

        session.selected_team_id = team_id
        session.auth_state = AppleAuthState.AUTHENTICATED
        return session

    async def create_distribution_certificate(
        self,
        apple_id: str,
        password: str,
        team_id: str,
        user_id: str,
        verification_code: str | None = None,
        team_name: str | None = None,
    ) -> dict[str, Any]:
        """Create an iOS Distribution Certificate using Spaceship.

        This creates a new distribution certificate if one doesn't exist,
        or returns information about existing certificates.

        Args:
            apple_id: Apple ID email
            password: Apple ID password
            team_id: Selected team ID
            user_id: The user's unique identifier (for session isolation)
            verification_code: Optional 2FA code (for Portal authentication)
            team_name: Team name (used to match Portal team if team_id is Tunes ID)

        Returns:
            Dict with certificate info (certificate_id, name, expiry, created)
        """
        # Get user-specific cookie path for session isolation
        cookie_path = self._get_user_cookie_path(user_id)

        loop = asyncio.get_event_loop()
        env = {
            'APPLE_ID': apple_id,
            'APPLE_PASSWORD': password,
            'TEAM_ID': team_id,
            'FASTLANE_DONT_STORE_PASSWORD': '1',
            'FASTLANE_SKIP_UPDATE_CHECK': '1',
            'SPACESHIP_COOKIE_PATH': cookie_path,  # User-specific session
        }
        if verification_code:
            env['VERIFICATION_CODE'] = verification_code
        if team_name:
            env['TEAM_NAME'] = team_name

        result = await loop.run_in_executor(
            None,
            self._run_ruby_script,
            FASTLANE_CREATE_CERTIFICATE_SCRIPT,
            env,
            180,  # 3 minute timeout for certificate creation
        )

        logger.info(f"Certificate creation result: {result}")

        if result.get('success'):
            return {
                'certificate_id': result.get('certificate_id'),
                'name': result.get('name'),
                'expiry': result.get('expiry'),
                'created': result.get('created', False),
                'existing_count': result.get('existing_count', 0),
            }
        else:
            error = result.get('error', 'unknown')
            message = result.get('message', 'Certificate creation failed')

            if error == 'max_certificates':
                from .exceptions import AppleCertificateError
                raise AppleCertificateError(
                    "Maximum number of iOS Distribution Certificates reached. "
                    "Please revoke an existing certificate in the Apple Developer Portal."
                )
            elif error == 'session_expired':
                from .exceptions import AppleSessionExpiredError
                raise AppleSessionExpiredError()
            else:
                from .exceptions import AppleCertificateError
                raise AppleCertificateError(message)

    async def register_bundle_id(
        self,
        apple_id: str,
        password: str,
        team_id: str,
        bundle_identifier: str,
        app_name: str,
        user_id: str,
        verification_code: str | None = None,
        team_name: str | None = None,
    ) -> dict[str, Any]:
        """Register a Bundle ID using Spaceship.

        Args:
            apple_id: Apple ID email
            password: Apple ID password
            team_id: Selected team ID
            bundle_identifier: The bundle ID (e.g., com.example.app)
            app_name: The app name
            user_id: The user's unique identifier (for session isolation)
            verification_code: Optional 2FA code (for Portal authentication)
            team_name: Team name (used to match Portal team if team_id is Tunes ID)

        Returns:
            Dict with bundle ID info (bundle_id, name, created)
        """
        # Get user-specific cookie path for session isolation
        cookie_path = self._get_user_cookie_path(user_id)

        loop = asyncio.get_event_loop()
        env = {
            'APPLE_ID': apple_id,
            'APPLE_PASSWORD': password,
            'TEAM_ID': team_id,
            'BUNDLE_IDENTIFIER': bundle_identifier,
            'APP_NAME': app_name,
            'FASTLANE_DONT_STORE_PASSWORD': '1',
            'FASTLANE_SKIP_UPDATE_CHECK': '1',
            'SPACESHIP_COOKIE_PATH': cookie_path,  # User-specific session
        }
        if verification_code:
            env['VERIFICATION_CODE'] = verification_code
        if team_name:
            env['TEAM_NAME'] = team_name

        result = await loop.run_in_executor(
            None,
            self._run_ruby_script,
            FASTLANE_REGISTER_BUNDLE_ID_SCRIPT,
            env,
            120,
        )

        logger.info(f"Bundle ID registration result: {result}")

        if result.get('success'):
            return {
                'bundle_id': result.get('bundle_id'),
                'name': result.get('name'),
                'created': result.get('created', False),
            }
        else:
            error = result.get('error', 'unknown')
            message = result.get('message', 'Bundle ID registration failed')

            if error == 'already_exists':
                # This is actually fine - bundle ID already exists
                return {
                    'bundle_id': bundle_identifier,
                    'name': app_name,
                    'created': False,
                }
            elif error == 'session_expired':
                from .exceptions import AppleSessionExpiredError
                raise AppleSessionExpiredError()
            else:
                from .exceptions import AppleBundleIdError
                raise AppleBundleIdError(message)

    async def create_app_store_connect_app(
        self,
        apple_id: str,
        password: str,
        team_id: str,
        bundle_identifier: str,
        app_name: str,
        user_id: str,
        verification_code: str | None = None,
        team_name: str | None = None,
    ) -> dict[str, Any]:
        """Create an App in App Store Connect.

        This creates the app record in App Store Connect, which is required
        for TestFlight submissions.

        Args:
            apple_id: Apple ID email
            password: Apple ID password
            team_id: Selected team ID
            bundle_identifier: The bundle ID (e.g., com.example.app)
            app_name: The app name
            user_id: The user's unique identifier (for session isolation)
            verification_code: Optional 2FA code
            team_name: Team name (used to match team)

        Returns:
            Dict with app info (app_id, bundle_id, name, created)
        """
        cookie_path = self._get_user_cookie_path(user_id)

        loop = asyncio.get_event_loop()
        env = {
            'APPLE_ID': apple_id,
            'APPLE_PASSWORD': password,
            'TEAM_ID': team_id,
            'BUNDLE_IDENTIFIER': bundle_identifier,
            'APP_NAME': app_name,
            'FASTLANE_DONT_STORE_PASSWORD': '1',
            'FASTLANE_SKIP_UPDATE_CHECK': '1',
            'SPACESHIP_COOKIE_PATH': cookie_path,
        }
        if verification_code:
            env['VERIFICATION_CODE'] = verification_code
        if team_name:
            env['TEAM_NAME'] = team_name

        result = await loop.run_in_executor(
            None,
            self._run_ruby_script,
            FASTLANE_CREATE_APP_SCRIPT,
            env,
            120,
        )

        logger.info(f"App Store Connect app creation result: {result}")

        if result.get('success'):
            return {
                'app_id': result.get('app_id'),
                'bundle_id': result.get('bundle_id'),
                'name': result.get('name'),
                'created': result.get('created', False),
            }
        else:
            error = result.get('error', 'unknown')
            message = result.get('message', 'App creation failed')
            conflict_type = result.get('conflict_type')

            if error == 'already_exists' and conflict_type == 'unknown':
                # Generic already exists with unknown conflict - treat as partial success
                # The app might be ours or might be a name/bundle conflict
                return {
                    'app_id': result.get('app_id'),
                    'bundle_id': bundle_identifier,
                    'name': app_name,
                    'created': False,
                }
            elif error == 'name_taken':
                # Name is globally unique and taken by someone else
                from .exceptions import AppleAppNameTakenError
                raise AppleAppNameTakenError(app_name, message)
            elif error == 'bundle_id_taken':
                # Bundle ID registered by another developer
                from .exceptions import AppleAppBundleIdTakenError
                raise AppleAppBundleIdTakenError(bundle_identifier, message)
            elif error == 'session_expired':
                raise AppleSessionExpiredError()
            else:
                raise AppleAuthenticationError(message)

    async def list_apps(
        self,
        apple_id: str,
        password: str,
        team_id: str,
        user_id: str,
        verification_code: str | None = None,
        team_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all apps from App Store Connect.

        Args:
            apple_id: Apple ID email
            password: Apple ID password
            team_id: Selected team ID
            user_id: The user's unique identifier (for session isolation)
            verification_code: Optional 2FA code
            team_name: Team name (used to match team)

        Returns:
            List of apps with (app_id, bundle_id, name, sku)
        """
        cookie_path = self._get_user_cookie_path(user_id)

        loop = asyncio.get_event_loop()
        env = {
            'APPLE_ID': apple_id,
            'APPLE_PASSWORD': password,
            'TEAM_ID': team_id,
            'FASTLANE_DONT_STORE_PASSWORD': '1',
            'FASTLANE_SKIP_UPDATE_CHECK': '1',
            'SPACESHIP_COOKIE_PATH': cookie_path,
        }
        if verification_code:
            env['VERIFICATION_CODE'] = verification_code
        if team_name:
            env['TEAM_NAME'] = team_name

        result = await loop.run_in_executor(
            None,
            self._run_ruby_script,
            FASTLANE_LIST_APPS_SCRIPT,
            env,
            60,
        )

        logger.info(f"List apps result: {result}")

        if result.get('success'):
            return result.get('apps', [])
        else:
            error = result.get('error', 'unknown')
            if error == 'session_expired':
                raise AppleSessionExpiredError()
            return []

    async def generate_eas_credentials(
        self,
        apple_id: str,
        password: str,
        team_id: str,
        bundle_identifier: str,
        user_id: str,
        verification_code: str | None = None,
        team_name: str | None = None,
    ) -> dict[str, Any]:
        """Generate credentials.json for EAS local builds.

        This creates or retrieves:
        - iOS Distribution Certificate (with private key if new)
        - App Store Provisioning Profile

        And returns them in credentials.json format for EAS.

        Args:
            apple_id: Apple ID email
            password: Apple ID password
            team_id: Selected team ID
            bundle_identifier: The bundle ID (e.g., com.example.app)
            user_id: The user's unique identifier (for session isolation)
            verification_code: Optional 2FA code
            team_name: Team name (used to match team)

        Returns:
            Dict with:
            - credentials: The credentials.json structure for EAS
            - certificate_id, certificate_name, certificate_expiry
            - profile_id, profile_name, profile_expiry
            - has_private_key: Whether a new certificate was created with private key
        """
        cookie_path = self._get_user_cookie_path(user_id)

        loop = asyncio.get_event_loop()
        env = {
            'APPLE_ID': apple_id,
            'APPLE_PASSWORD': password,
            'TEAM_ID': team_id,
            'BUNDLE_IDENTIFIER': bundle_identifier,
            'FASTLANE_DONT_STORE_PASSWORD': '1',
            'FASTLANE_SKIP_UPDATE_CHECK': '1',
            'SPACESHIP_COOKIE_PATH': cookie_path,
        }
        if verification_code:
            env['VERIFICATION_CODE'] = verification_code
        if team_name:
            env['TEAM_NAME'] = team_name

        result = await loop.run_in_executor(
            None,
            self._run_ruby_script,
            FASTLANE_GENERATE_EAS_CREDENTIALS_SCRIPT,
            env,
            300,  # 5 minute timeout for credential generation
        )

        logger.info(f"EAS credentials generation result: {result}")

        if result.get('success'):
            return {
                'p12_base64': result.get('p12_base64'),
                'p12_password': result.get('p12_password', ''),
                'provisioning_profile_base64': result.get('provisioning_profile_base64'),
                'certificate_id': result.get('certificate_id'),
                'certificate_name': result.get('certificate_name'),
                'certificate_expiry': result.get('certificate_expiry'),
                'profile_id': result.get('profile_id'),
                'profile_name': result.get('profile_name'),
                'profile_expiry': result.get('profile_expiry'),
                'has_private_key': result.get('has_private_key', False),
                'message': result.get('message'),
            }
        else:
            error = result.get('error', 'unknown')
            message = result.get('message', 'Credential generation failed')

            if error == 'max_certificates':
                raise AppleCertificateError(
                    "Maximum number of iOS Distribution Certificates reached. "
                    "Please revoke an existing certificate in the Apple Developer Portal."
                )
            elif error == 'session_expired':
                raise AppleSessionExpiredError()
            elif error == 'bundle_id_not_found':
                raise AppleBundleIdError(
                    f"Bundle ID {bundle_identifier} not registered. "
                    "Please complete the App Setup step first."
                )
            else:
                raise AppleCertificateError(message)
