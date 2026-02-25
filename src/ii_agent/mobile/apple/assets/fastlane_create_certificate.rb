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
