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
