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
