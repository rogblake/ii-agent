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
