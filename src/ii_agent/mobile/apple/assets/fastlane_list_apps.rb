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
