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
