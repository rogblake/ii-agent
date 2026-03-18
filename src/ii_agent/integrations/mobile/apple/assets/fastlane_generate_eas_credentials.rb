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
