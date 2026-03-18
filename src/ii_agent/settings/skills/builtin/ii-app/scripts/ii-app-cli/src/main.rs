use anyhow::{anyhow, bail, Context, Result};
use clap::{Args, Parser, Subcommand};
use reqwest::blocking::Client;
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::env;
use std::fs;
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use walkdir::WalkDir;

const APP_CACHE_DIR_NAME: &str = ".ii-app";
const WEB_CACHE_FILE_NAME: &str = "web.json";
const MOBILE_CACHE_FILE_NAME: &str = "mobile.json";
const LEGACY_WEB_CACHE_DIR_NAME: &str = ".ii-web-server";
const LEGACY_WEB_CACHE_FILE_NAME: &str = "cache.json";
const SCREENSHOT_DIR_NAME: &str = "shots";
const STATUS_DIR_NAME: &str = "status";
const PORT_PLACEHOLDER: &str = "{PORT}";
const DEFAULT_EXPO_WEB_PORT: u16 = 8081;
const DEFAULT_STRIPE_TIMEOUT_SECONDS: u64 = 60;
const EXPO_STARTUP_ATTEMPTS: usize = 20;
const EXPO_POLL_INTERVAL: Duration = Duration::from_millis(1500);

#[derive(Parser)]
#[command(
    name = "ii-app",
    bin_name = "ii-app",
    version,
    about = "Initialize and manage local web and mobile app projects."
)]
struct Cli {
    #[command(subcommand)]
    command: AppCommands,
}

#[derive(Subcommand)]
enum AppCommands {
    Web(WebArgs),
    Mobile(MobileArgs),
    Stripe(StripeArgs),
}

#[derive(Args)]
struct WebArgs {
    #[command(subcommand)]
    command: WebCommands,
}

#[derive(Subcommand)]
enum WebCommands {
    ListTemplates(ListTemplatesArgs),
    Init(WebInitArgs),
    Restart(WebRestartArgs),
    ViewLog(WebViewLogArgs),
    Screenshot(WebScreenshotArgs),
    Status(WebStatusArgs),
}

#[derive(Args)]
struct MobileArgs {
    #[command(subcommand)]
    command: MobileCommands,
}

#[derive(Subcommand)]
enum MobileCommands {
    Init(MobileInitArgs),
    Restart(MobileRestartArgs),
    ViewLog(MobileViewLogArgs),
}

#[derive(Args)]
struct StripeArgs {
    #[command(subcommand)]
    command: StripeCommands,
}

#[derive(Subcommand)]
enum StripeCommands {
    RegisterWebhook(StripeRegisterWebhookArgs),
}

#[derive(Args)]
struct ListTemplatesArgs {
    #[arg(long)]
    json: bool,
}

#[derive(Args)]
struct WebInitArgs {
    template_id: String,
    #[arg(long)]
    project_name: Option<String>,
    #[arg(long, default_value = ".")]
    workspace: PathBuf,
    #[arg(long)]
    cache_path: Option<PathBuf>,
    #[arg(long)]
    host_url: Option<String>,
    #[arg(long)]
    database_url: Option<String>,
    #[arg(long)]
    skip_install: bool,
    #[arg(long)]
    skip_start: bool,
    #[arg(long)]
    json: bool,
}

#[derive(Args)]
struct WebRestartArgs {
    #[arg(long, default_value = ".")]
    workspace: PathBuf,
    #[arg(long)]
    cache_path: Option<PathBuf>,
    #[arg(long)]
    json: bool,
}

#[derive(Args)]
struct WebViewLogArgs {
    #[arg(long, default_value = ".")]
    workspace: PathBuf,
    #[arg(long)]
    cache_path: Option<PathBuf>,
    #[arg(long)]
    session: Option<String>,
    #[arg(long, default_value_t = 200)]
    lines: usize,
    #[arg(long)]
    json: bool,
}

#[derive(Args)]
struct WebScreenshotArgs {
    #[arg(long, default_value = ".")]
    workspace: PathBuf,
    #[arg(long)]
    cache_path: Option<PathBuf>,
    #[arg(long)]
    output: Option<PathBuf>,
    #[arg(long)]
    screenshot_dir: Option<PathBuf>,
    #[arg(long)]
    annotate: bool,
    #[arg(long, default_value = "png")]
    screenshot_format: String,
    #[arg(long)]
    screenshot_quality: Option<u8>,
    #[arg(long)]
    json: bool,
}

#[derive(Args)]
struct WebStatusArgs {
    #[arg(long, default_value = ".")]
    workspace: PathBuf,
    #[arg(long)]
    cache_path: Option<PathBuf>,
    #[arg(long)]
    session: Option<String>,
    #[arg(long, default_value_t = 200)]
    lines: usize,
    #[arg(long)]
    output_dir: Option<PathBuf>,
    #[arg(long)]
    annotate: bool,
    #[arg(long, default_value = "png")]
    screenshot_format: String,
    #[arg(long)]
    screenshot_quality: Option<u8>,
    #[arg(long)]
    json: bool,
}

#[derive(Args)]
struct MobileInitArgs {
    project_name: String,
    #[arg(long, default_value = ".")]
    workspace: PathBuf,
    #[arg(long)]
    cache_path: Option<PathBuf>,
    #[arg(long, default_value = "tabs")]
    template: String,
    #[arg(long)]
    example: Option<String>,
    #[arg(long)]
    no_tailwind: bool,
    #[arg(long)]
    skip_install: bool,
    #[arg(long)]
    skip_start: bool,
    #[arg(long)]
    json: bool,
}

#[derive(Args)]
struct MobileRestartArgs {
    #[arg(long, default_value = ".")]
    workspace: PathBuf,
    #[arg(long)]
    cache_path: Option<PathBuf>,
    #[arg(long)]
    json: bool,
}

#[derive(Args)]
struct MobileViewLogArgs {
    #[arg(long, default_value = ".")]
    workspace: PathBuf,
    #[arg(long)]
    cache_path: Option<PathBuf>,
    #[arg(long)]
    session: Option<String>,
    #[arg(long, default_value_t = 200)]
    lines: usize,
    #[arg(long)]
    json: bool,
}

#[derive(Args)]
struct StripeRegisterWebhookArgs {
    #[arg(long)]
    stripe_secret_key: String,
    #[arg(long)]
    endpoint_url: String,
    #[arg(long)]
    project_directory: PathBuf,
    #[arg(long, default_value = ".")]
    workspace: PathBuf,
    #[arg(long = "event", value_delimiter = ',')]
    events: Vec<String>,
    #[arg(long, default_value = "Webhook registered via ii-app")]
    description: String,
    #[arg(long)]
    json: bool,
}

#[derive(Clone, Serialize, Deserialize)]
struct ServerConfig {
    deployment_url: String,
    port: u16,
    command: String,
    session: String,
    run_dir: String,
}

#[derive(Clone, Serialize, Deserialize)]
struct DeploymentConfig {
    preview_url: String,
    preview_port: u16,
    project_name: String,
    framework: String,
    directory: String,
    env_file: Option<String>,
    servers: Vec<ServerConfig>,
}

#[derive(Clone, Serialize, Deserialize)]
struct WebCacheFile {
    version: u32,
    deployment_config: DeploymentConfig,
}

#[derive(Clone, Serialize, Deserialize)]
struct MobileAppConfig {
    project_name: String,
    project_dir: String,
    template: String,
    example: Option<String>,
    with_tailwind: bool,
    web_port: u16,
    session: String,
    tunnel_url: Option<String>,
    qr_code_value: Option<String>,
    web_url: Option<String>,
    startup_mode: Option<String>,
}

#[derive(Clone, Serialize, Deserialize)]
struct MobileCacheFile {
    version: u32,
    mobile_app_config: MobileAppConfig,
}

#[derive(Clone, Copy)]
struct InstallStep {
    run_dir_suffix: &'static str,
    command: &'static str,
}

#[derive(Clone, Copy)]
struct ServerTemplate {
    role: &'static str,
    run_dir_suffix: &'static str,
    port: u16,
    command: &'static str,
}

#[derive(Clone, Copy)]
struct TemplateSpec {
    id: &'static str,
    description: &'static str,
    preview_role: &'static str,
    install_steps: &'static [InstallStep],
    servers: &'static [ServerTemplate],
}

#[derive(Serialize)]
struct TemplateInfo {
    id: &'static str,
    description: &'static str,
}

#[derive(Serialize)]
struct RestartServerResult {
    name: String,
    session: String,
    url: String,
    port: u16,
    session_output: String,
}

#[derive(Serialize)]
struct WebRestartOutput {
    preview_url: String,
    preview_port: u16,
    servers: Vec<RestartServerResult>,
}

#[derive(Serialize)]
struct LogOutput {
    session: String,
    url: Option<String>,
    output: String,
}

#[derive(Serialize)]
struct ScreenshotOutput {
    url: String,
    path: String,
}

#[derive(Serialize)]
struct StatusOutput {
    session: String,
    url: Option<String>,
    log_path: String,
    screenshot_path: Option<String>,
    status_path: String,
}

#[derive(Serialize)]
struct StripeRegisterWebhookOutput {
    webhook_endpoint_id: String,
    endpoint_url: String,
    events: Vec<String>,
    env_file_updated: String,
}

#[derive(Deserialize)]
struct StripeWebhookApiResponse {
    id: String,
    secret: Option<String>,
}

#[derive(Serialize)]
struct ExpoStartupResult {
    success: bool,
    tunnel_url: Option<String>,
    qr_code_value: Option<String>,
    web_url: Option<String>,
    startup_mode: Option<String>,
    warning: Option<String>,
    error: Option<String>,
}

const NEXTJS_INSTALL: &[InstallStep] = &[InstallStep {
    run_dir_suffix: "",
    command: "bun install",
}];

const NEXTJS_SERVERS: &[ServerTemplate] = &[ServerTemplate {
    role: "fullstack",
    run_dir_suffix: "",
    port: 3000,
    command: "PORT={PORT} bun run dev",
}];

const REACT_PYTHON_INSTALL: &[InstallStep] = &[
    InstallStep {
        run_dir_suffix: "frontend",
        command: "bun install",
    },
    InstallStep {
        run_dir_suffix: "backend",
        command: "pip install -r requirements.txt",
    },
];

const REACT_PYTHON_SERVERS: &[ServerTemplate] = &[
    ServerTemplate {
        role: "backend",
        run_dir_suffix: "backend",
        port: 8000,
        command: "uvicorn src.main:app --host 0.0.0.0 --port {PORT} --reload",
    },
    ServerTemplate {
        role: "frontend",
        run_dir_suffix: "frontend",
        port: 3000,
        command: "bun run dev -- --host --port {PORT}",
    },
];

const REACT_VITE_INSTALL: &[InstallStep] = &[InstallStep {
    run_dir_suffix: "",
    command: "bun install",
}];

const REACT_VITE_SERVERS: &[ServerTemplate] = &[ServerTemplate {
    role: "frontend",
    run_dir_suffix: "",
    port: 3000,
    command: "bun run dev -- --host --port {PORT}",
}];

const TEMPLATE_SPECS: &[TemplateSpec] = &[
    TemplateSpec {
        id: "nextjs-shadcn",
        description: "Next.js + shadcn/ui single-server template",
        preview_role: "fullstack",
        install_steps: NEXTJS_INSTALL,
        servers: NEXTJS_SERVERS,
    },
    TemplateSpec {
        id: "react-shadcn-python",
        description: "React + shadcn/ui frontend with FastAPI backend",
        preview_role: "frontend",
        install_steps: REACT_PYTHON_INSTALL,
        servers: REACT_PYTHON_SERVERS,
    },
    TemplateSpec {
        id: "react-tailwind-python",
        description: "React + Tailwind frontend with FastAPI backend",
        preview_role: "frontend",
        install_steps: REACT_PYTHON_INSTALL,
        servers: REACT_PYTHON_SERVERS,
    },
    TemplateSpec {
        id: "react-vite-shadcn",
        description: "Vite + shadcn/ui frontend template",
        preview_role: "frontend",
        install_steps: REACT_VITE_INSTALL,
        servers: REACT_VITE_SERVERS,
    },
];

const MOBILE_TEMPLATES: &[&str] = &["tabs", "blank", "blank-typescript"];
const DEFAULT_STRIPE_EVENTS: &[&str] = &[
    "checkout.session.completed",
    "checkout.session.expired",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_succeeded",
    "invoice.payment_failed",
    "payment_intent.succeeded",
    "payment_intent.payment_failed",
];
const EXPO_READY_MARKERS: &[&str] = &[
    "Metro waiting on",
    "Tunnel ready",
    "Web is waiting on",
    "Waiting on http://",
    "Logs for your project will appear below",
];
const EXPO_ERROR_PATTERNS: &[&str] = &[
    "assertionerror",
    "typeerror:",
    "syntaxerror:",
    "cannot find module",
    "module not found",
    "enoent",
    "eacces",
    "command failed",
    "fatal:",
    "commanderror:",
];

fn main() -> Result<()> {
    let cli = Cli::parse();
    match cli.command {
        AppCommands::Web(args) => run_web(args),
        AppCommands::Mobile(args) => run_mobile(args),
        AppCommands::Stripe(args) => run_stripe(args),
    }
}

fn run_web(args: WebArgs) -> Result<()> {
    match args.command {
        WebCommands::ListTemplates(args) => cmd_web_list_templates(args),
        WebCommands::Init(args) => cmd_web_init(args),
        WebCommands::Restart(args) => cmd_web_restart(args),
        WebCommands::ViewLog(args) => cmd_web_view_log(args),
        WebCommands::Screenshot(args) => cmd_web_screenshot(args),
        WebCommands::Status(args) => cmd_web_status(args),
    }
}

fn run_mobile(args: MobileArgs) -> Result<()> {
    match args.command {
        MobileCommands::Init(args) => cmd_mobile_init(args),
        MobileCommands::Restart(args) => cmd_mobile_restart(args),
        MobileCommands::ViewLog(args) => cmd_mobile_view_log(args),
    }
}

fn run_stripe(args: StripeArgs) -> Result<()> {
    match args.command {
        StripeCommands::RegisterWebhook(args) => cmd_stripe_register_webhook(args),
    }
}

fn cmd_web_list_templates(args: ListTemplatesArgs) -> Result<()> {
    let templates: Vec<TemplateInfo> = TEMPLATE_SPECS
        .iter()
        .map(|spec| TemplateInfo {
            id: spec.id,
            description: spec.description,
        })
        .collect();

    if args.json {
        print_json(&templates)?;
        return Ok(());
    }

    for template in templates {
        println!("{}\n  {}", template.id, template.description);
    }
    Ok(())
}

fn cmd_web_init(args: WebInitArgs) -> Result<()> {
    let skill_root = discover_skill_root()?;
    let workspace = resolve_path(&args.workspace)?;
    fs::create_dir_all(&workspace)
        .with_context(|| format!("failed to create workspace {}", workspace.display()))?;

    let cache_path = resolve_web_cache_path(args.cache_path.as_deref(), &workspace);
    let legacy_cache = default_legacy_web_cache_path(&workspace);
    if cache_path.exists() || legacy_cache.exists() {
        let existing_path = if cache_path.exists() {
            cache_path
        } else {
            legacy_cache
        };
        let existing: WebCacheFile = load_json_file(&existing_path)?;
        bail!(
            "web cache already exists at {} for project {}",
            existing_path.display(),
            existing.deployment_config.project_name
        );
    }

    let spec = get_template_spec(&args.template_id)?;
    let project_name = args
        .project_name
        .clone()
        .unwrap_or_else(|| args.template_id.clone());
    validate_project_name(&project_name)?;

    let project_dir = workspace.join(&project_name);
    if project_dir.exists() {
        bail!(
            "project directory already exists: {}",
            project_dir.display()
        );
    }

    let template_dir = skill_root.join("assets").join("templates").join(spec.id);
    if !template_dir.is_dir() {
        bail!("template directory not found: {}", template_dir.display());
    }

    copy_dir_recursive(&template_dir, &project_dir)?;

    let env_file = if let Some(database_url) = args.database_url.as_deref() {
        let env_path = project_dir.join(".env");
        fs::write(&env_path, format!("DATABASE_URL={database_url}\n"))
            .with_context(|| format!("failed to write {}", env_path.display()))?;
        Some(env_path)
    } else {
        None
    };

    if !args.skip_install {
        for step in spec.install_steps {
            let run_dir = join_suffix(&project_dir, step.run_dir_suffix);
            run_shell_command(step.command, &run_dir)?;
        }
    }

    let (mut servers, preview_session) =
        instantiate_web_servers(spec, &project_name, &project_dir, args.host_url.as_deref());

    if !args.skip_start {
        for server in &mut servers {
            start_web_server(server, env_file.as_deref(), args.host_url.as_deref())?;
            wait_for_port(server.port, Duration::from_secs(10))
                .with_context(|| format!("server {} did not become ready", server.session))?;
        }
    }

    let preview_server = servers
        .iter()
        .find(|server| server.session == preview_session)
        .ok_or_else(|| anyhow!("preview session not found after init"))?;

    let deployment = DeploymentConfig {
        preview_url: preview_server.deployment_url.clone(),
        preview_port: preview_server.port,
        project_name,
        framework: spec.id.to_string(),
        directory: project_dir.to_string_lossy().to_string(),
        env_file: env_file.map(|path| path.to_string_lossy().to_string()),
        servers,
    };

    save_json_file(
        &cache_path,
        &WebCacheFile {
            version: 1,
            deployment_config: deployment.clone(),
        },
    )?;

    if args.json {
        print_json(&deployment)?;
        return Ok(());
    }

    println!("Initialized web app {}", deployment.framework);
    println!("Project: {}", deployment.directory);
    println!("Preview: {}", deployment.preview_url);
    println!("Cache: {}", cache_path.display());
    for server in &deployment.servers {
        println!("Session: {} -> {}", server.session, server.deployment_url);
    }

    Ok(())
}

fn cmd_web_restart(args: WebRestartArgs) -> Result<()> {
    let workspace = resolve_path(&args.workspace)?;
    let cache_path = discover_existing_web_cache_path(args.cache_path.as_deref(), &workspace)?;
    let mut cache: WebCacheFile = load_json_file(&cache_path)?;

    let env_file = cache.deployment_config.env_file.clone().map(PathBuf::from);
    let host_url = extract_host_url(&cache.deployment_config.preview_url);

    let previous_preview_port = cache.deployment_config.preview_port;
    let mut preview_url = cache.deployment_config.preview_url.clone();
    let mut preview_port = previous_preview_port;
    let mut results = Vec::new();

    for server in &mut cache.deployment_config.servers {
        let was_preview = server.port == previous_preview_port;
        let result = restart_web_server(server, env_file.as_deref(), host_url.as_deref())?;
        if was_preview {
            preview_url = server.deployment_url.clone();
            preview_port = server.port;
        }
        results.push(result);
    }

    cache.deployment_config.preview_url = preview_url.clone();
    cache.deployment_config.preview_port = preview_port;
    save_json_file(&cache_path, &cache)?;

    let output = WebRestartOutput {
        preview_url,
        preview_port,
        servers: results,
    };

    if args.json {
        print_json(&output)?;
        return Ok(());
    }

    println!("Restarted web servers");
    println!("Preview: {}", output.preview_url);
    for server in &output.servers {
        println!("{} -> {}", server.session, server.url);
    }
    Ok(())
}

fn cmd_web_view_log(args: WebViewLogArgs) -> Result<()> {
    let workspace = resolve_path(&args.workspace)?;
    let cache_path = discover_existing_web_cache_path(args.cache_path.as_deref(), &workspace)?;
    let cache: WebCacheFile = load_json_file(&cache_path)?;

    let session = args
        .session
        .clone()
        .unwrap_or_else(|| default_web_session(&cache.deployment_config));
    let output = capture_session_output(&session, args.lines)?;
    let url = cache
        .deployment_config
        .servers
        .iter()
        .find(|server| server.session == session)
        .map(|server| server.deployment_url.clone());

    let payload = LogOutput {
        session,
        url,
        output,
    };
    if args.json {
        print_json(&payload)?;
        return Ok(());
    }

    if let Some(url) = &payload.url {
        println!("URL: {url}");
    }
    println!("Session: {}", payload.session);
    println!("{}", payload.output);
    Ok(())
}

fn cmd_web_screenshot(args: WebScreenshotArgs) -> Result<()> {
    let workspace = resolve_path(&args.workspace)?;
    let cache_path = discover_existing_web_cache_path(args.cache_path.as_deref(), &workspace)?;
    let cache: WebCacheFile = load_json_file(&cache_path)?;
    let url = cache.deployment_config.preview_url.clone();
    validate_preview_url(&url)?;

    let screenshot_format = normalize_screenshot_format(&args.screenshot_format)?;
    let output_path = resolve_screenshot_output_path(
        args.output.as_deref(),
        args.screenshot_dir.as_deref(),
        &workspace,
        cache.deployment_config.preview_port,
        screenshot_format,
    )?;

    run_agent_browser_screenshot(
        &url,
        &output_path,
        args.annotate,
        screenshot_format,
        args.screenshot_quality,
    )?;

    let payload = ScreenshotOutput {
        url,
        path: output_path.to_string_lossy().to_string(),
    };
    if args.json {
        print_json(&payload)?;
        return Ok(());
    }

    println!("{}", payload.path);
    Ok(())
}

fn cmd_web_status(args: WebStatusArgs) -> Result<()> {
    let workspace = resolve_path(&args.workspace)?;
    let cache_path = discover_existing_web_cache_path(args.cache_path.as_deref(), &workspace)?;
    let cache: WebCacheFile = load_json_file(&cache_path)?;
    let default_session = default_web_session(&cache.deployment_config);
    let session = args
        .session
        .clone()
        .unwrap_or_else(|| default_session.clone());
    let output = capture_session_output(&session, args.lines)?;
    let url = cache
        .deployment_config
        .servers
        .iter()
        .find(|server| server.session == session)
        .map(|server| server.deployment_url.clone())
        .or_else(|| {
            if session == default_session {
                Some(cache.deployment_config.preview_url.clone())
            } else {
                None
            }
        });

    let screenshot_format = normalize_screenshot_format(&args.screenshot_format)?;
    let status_dir = resolve_status_dir(args.output_dir.as_deref(), &workspace);
    fs::create_dir_all(&status_dir)
        .with_context(|| format!("failed to create {}", status_dir.display()))?;

    let timestamp = unix_timestamp_seconds()?;
    let base_name = format!(
        "web-status-{}-{timestamp}",
        cache.deployment_config.preview_port
    );
    let log_path = status_dir.join(format!("{base_name}.log"));
    fs::write(&log_path, &output)
        .with_context(|| format!("failed to write {}", log_path.display()))?;

    let screenshot_path = if let Some(url) = url.as_deref() {
        if is_previewable_url(url) {
            let path = status_dir.join(format!("{base_name}.{screenshot_format}"));
            run_agent_browser_screenshot(
                url,
                &path,
                args.annotate,
                screenshot_format,
                args.screenshot_quality,
            )?;
            Some(path)
        } else {
            None
        }
    } else {
        None
    };

    let status_path = status_dir.join(format!("{base_name}.json"));
    let payload = StatusOutput {
        session,
        url,
        log_path: log_path.to_string_lossy().to_string(),
        screenshot_path: screenshot_path
            .as_ref()
            .map(|path| path.to_string_lossy().to_string()),
        status_path: status_path.to_string_lossy().to_string(),
    };
    save_json_file(&status_path, &payload)?;

    if args.json {
        print_json(&payload)?;
        return Ok(());
    }

    println!("{}", payload.status_path);
    Ok(())
}

fn cmd_mobile_init(args: MobileInitArgs) -> Result<()> {
    let workspace = resolve_path(&args.workspace)?;
    fs::create_dir_all(&workspace)
        .with_context(|| format!("failed to create workspace {}", workspace.display()))?;

    validate_project_name(&args.project_name)?;
    validate_mobile_template(&args.template)?;

    let cache_path = resolve_mobile_cache_path(args.cache_path.as_deref(), &workspace);
    if cache_path.exists() {
        let existing: MobileCacheFile = load_json_file(&cache_path)?;
        bail!(
            "mobile cache already exists at {} for project {}",
            cache_path.display(),
            existing.mobile_app_config.project_name
        );
    }

    let project_dir = workspace.join(&args.project_name);
    if project_dir.exists() {
        bail!(
            "project directory already exists: {}",
            project_dir.display()
        );
    }

    run_shell_command(
        &build_mobile_create_command(&args.project_name, &args.template, args.example.as_deref())?,
        &workspace,
    )?;

    if !args.skip_install {
        install_mobile_dependencies(&project_dir, !args.no_tailwind)?;
    }

    let session = mobile_session_name(&args.project_name);
    let mut mobile_config = MobileAppConfig {
        project_name: args.project_name.clone(),
        project_dir: project_dir.to_string_lossy().to_string(),
        template: args.template.clone(),
        example: args.example.clone(),
        with_tailwind: !args.no_tailwind,
        web_port: DEFAULT_EXPO_WEB_PORT,
        session: session.clone(),
        tunnel_url: None,
        qr_code_value: None,
        web_url: None,
        startup_mode: None,
    };

    if !args.skip_start {
        let result = start_expo_server(&session, &project_dir)?;
        if !result.success {
            let message = result
                .error
                .unwrap_or_else(|| "Expo startup failed".to_string());
            bail!("{message}");
        }
        mobile_config.tunnel_url = result.tunnel_url;
        mobile_config.qr_code_value = result.qr_code_value;
        mobile_config.web_url = result.web_url;
        mobile_config.startup_mode = result.startup_mode;
    }

    save_json_file(
        &cache_path,
        &MobileCacheFile {
            version: 1,
            mobile_app_config: mobile_config.clone(),
        },
    )?;

    if args.json {
        print_json(&mobile_config)?;
        return Ok(());
    }

    println!("Initialized mobile app {}", mobile_config.project_name);
    println!("Project: {}", mobile_config.project_dir);
    println!("Session: {}", mobile_config.session);
    if let Some(web_url) = &mobile_config.web_url {
        println!("Web URL: {web_url}");
    }
    if let Some(tunnel_url) = &mobile_config.tunnel_url {
        println!("Tunnel URL: {tunnel_url}");
    }
    println!("Cache: {}", cache_path.display());
    Ok(())
}

fn cmd_mobile_restart(args: MobileRestartArgs) -> Result<()> {
    let workspace = resolve_path(&args.workspace)?;
    let cache_path = resolve_mobile_cache_path(args.cache_path.as_deref(), &workspace);
    let mut cache: MobileCacheFile = load_json_file(&cache_path)?;
    let project_dir = PathBuf::from(&cache.mobile_app_config.project_dir);
    let session = cache.mobile_app_config.session.clone();

    let result = start_expo_server(&session, &project_dir)?;
    if !result.success {
        let message = result
            .error
            .unwrap_or_else(|| "Expo startup failed".to_string());
        bail!("{message}");
    }

    cache.mobile_app_config.tunnel_url = result.tunnel_url;
    cache.mobile_app_config.qr_code_value = result.qr_code_value;
    cache.mobile_app_config.web_url = result.web_url;
    cache.mobile_app_config.startup_mode = result.startup_mode;
    save_json_file(&cache_path, &cache)?;

    if args.json {
        print_json(&cache.mobile_app_config)?;
        return Ok(());
    }

    println!(
        "Restarted mobile app {}",
        cache.mobile_app_config.project_name
    );
    println!("Session: {}", cache.mobile_app_config.session);
    if let Some(web_url) = &cache.mobile_app_config.web_url {
        println!("Web URL: {web_url}");
    }
    if let Some(tunnel_url) = &cache.mobile_app_config.tunnel_url {
        println!("Tunnel URL: {tunnel_url}");
    }
    Ok(())
}

fn cmd_mobile_view_log(args: MobileViewLogArgs) -> Result<()> {
    let workspace = resolve_path(&args.workspace)?;
    let cache_path = resolve_mobile_cache_path(args.cache_path.as_deref(), &workspace);
    let cache: MobileCacheFile = load_json_file(&cache_path)?;

    let session = args
        .session
        .clone()
        .unwrap_or_else(|| cache.mobile_app_config.session.clone());
    let output = capture_session_output(&session, args.lines)?;
    let url = cache
        .mobile_app_config
        .web_url
        .clone()
        .or_else(|| cache.mobile_app_config.tunnel_url.clone());

    let payload = LogOutput {
        session,
        url,
        output,
    };
    if args.json {
        print_json(&payload)?;
        return Ok(());
    }

    if let Some(url) = &payload.url {
        println!("URL: {url}");
    }
    println!("Session: {}", payload.session);
    println!("{}", payload.output);
    Ok(())
}

fn cmd_stripe_register_webhook(args: StripeRegisterWebhookArgs) -> Result<()> {
    validate_stripe_secret_key(&args.stripe_secret_key)?;
    validate_https_url(&args.endpoint_url, "endpoint url")?;

    let workspace = resolve_path(&args.workspace)?;
    let project_dir = resolve_existing_directory(&args.project_directory, &workspace)?;
    let events = normalize_stripe_events(&args.events);
    let idempotency_key = generate_stripe_idempotency_key(&args.endpoint_url);

    let api_response = register_stripe_webhook(
        &args.stripe_secret_key,
        &args.endpoint_url,
        &events,
        &args.description,
        &idempotency_key,
    )?;
    let webhook_secret = api_response.secret.ok_or_else(|| {
        anyhow!(
            "Stripe did not return a webhook signing secret. The webhook may already exist; check Stripe Dashboard for endpoint {}",
            api_response.id
        )
    })?;

    let env_path = project_dir.join(".env");
    write_env_key(&env_path, "STRIPE_WEBHOOK_SECRET", &webhook_secret, false)?;

    let payload = StripeRegisterWebhookOutput {
        webhook_endpoint_id: api_response.id,
        endpoint_url: args.endpoint_url,
        events,
        env_file_updated: env_path.to_string_lossy().to_string(),
    };
    if args.json {
        print_json(&payload)?;
        return Ok(());
    }

    println!("Registered Stripe webhook {}", payload.webhook_endpoint_id);
    println!("Endpoint: {}", payload.endpoint_url);
    println!("Env file: {}", payload.env_file_updated);
    println!("Restart the relevant server if it already loaded environment variables.");
    Ok(())
}

fn instantiate_web_servers(
    spec: TemplateSpec,
    project_name: &str,
    project_dir: &Path,
    host_url: Option<&str>,
) -> (Vec<ServerConfig>, String) {
    let mut preview_session = String::new();
    let servers = spec
        .servers
        .iter()
        .map(|server| {
            let session = web_session_name(project_name, server.role);
            if server.role == spec.preview_role {
                preview_session = session.clone();
            }
            ServerConfig {
                deployment_url: deployment_url(server.port, host_url),
                port: server.port,
                command: server.command.to_string(),
                session,
                run_dir: join_suffix(project_dir, server.run_dir_suffix)
                    .to_string_lossy()
                    .to_string(),
            }
        })
        .collect();
    (servers, preview_session)
}

fn restart_web_server(
    server: &mut ServerConfig,
    env_file: Option<&Path>,
    host_url: Option<&str>,
) -> Result<RestartServerResult> {
    stop_session_command(&server.session)?;
    ensure_session(&server.session, Path::new(&server.run_dir))?;

    let start_port = server.port;
    let command = if server.command.contains(PORT_PLACEHOLDER) {
        let port = find_available_port(start_port)?;
        server.port = port;
        server.command.replace(PORT_PLACEHOLDER, &port.to_string())
    } else {
        server.port = start_port;
        server.command.clone()
    };

    server.deployment_url = deployment_url(server.port, host_url);
    send_command_to_session(&server.session, &server.run_dir, env_file, &command)?;
    wait_for_port(server.port, Duration::from_secs(10))
        .with_context(|| format!("server {} did not become ready", server.session))?;
    let session_output = capture_session_output(&server.session, 120)?;

    Ok(RestartServerResult {
        name: server.session.clone(),
        session: server.session.clone(),
        url: server.deployment_url.clone(),
        port: server.port,
        session_output,
    })
}

fn start_web_server(
    server: &mut ServerConfig,
    env_file: Option<&Path>,
    host_url: Option<&str>,
) -> Result<()> {
    ensure_session(&server.session, Path::new(&server.run_dir))?;

    let command = if server.command.contains(PORT_PLACEHOLDER) {
        let port = find_available_port(server.port)?;
        server.port = port;
        server.command.replace(PORT_PLACEHOLDER, &port.to_string())
    } else {
        server.command.clone()
    };

    server.deployment_url = deployment_url(server.port, host_url);
    send_command_to_session(&server.session, &server.run_dir, env_file, &command)
}

fn build_mobile_create_command(
    project_name: &str,
    template: &str,
    example: Option<&str>,
) -> Result<String> {
    let project_name = shell_quote(project_name);
    if let Some(example) = example {
        return Ok(format!(
            "bunx create-expo-app@latest {project_name} --example {} --no-install",
            shell_quote(example)
        ));
    }

    let template_flag = match template {
        "tabs" => "tabs",
        "blank" => "default",
        "blank-typescript" => "blank-typescript",
        _ => bail!("unsupported mobile template `{template}`"),
    };

    Ok(format!(
        "bunx create-expo-app@latest {project_name} --template {template_flag}@sdk-54 --no-install"
    ))
}

fn install_mobile_dependencies(project_dir: &Path, with_tailwind: bool) -> Result<()> {
    run_shell_command("bun install", project_dir)?;
    run_shell_command(
        "bunx expo install expo-splash-screen expo-status-bar expo-system-ui",
        project_dir,
    )?;
    run_shell_command("bun add -d @expo/ngrok", project_dir)?;
    run_shell_command("bunx expo install react-dom react-native-web", project_dir)?;

    if with_tailwind {
        let tailwind_deps = concat!(
            "bunx expo install ",
            "tailwindcss@^4 nativewind@5.0.0-preview.2 ",
            "react-native-css@0.0.0-nightly.5ce6396 ",
            "@tailwindcss/postcss tailwind-merge clsx"
        );
        run_shell_command(tailwind_deps, project_dir)?;
    }

    Ok(())
}

fn start_expo_server(session: &str, project_dir: &Path) -> Result<ExpoStartupResult> {
    ensure_session(session, project_dir)?;

    let attempts = [
        (
            "tunnel",
            "EXPO_FORCE_WEBCONTAINER_ENV=1 bunx expo start --tunnel --web",
            true,
        ),
        ("lan", "bunx expo start --lan --web", false),
    ];

    let mut errors = Vec::new();

    for (index, (mode, command, require_tunnel)) in attempts.iter().enumerate() {
        send_command_to_session(session, &project_dir.to_string_lossy(), None, command)?;

        let result = poll_expo_startup(session, mode, *require_tunnel)?;
        if result.success {
            return Ok(result);
        }

        errors.push(format!(
            "[{mode}] {}",
            result
                .error
                .clone()
                .unwrap_or_else(|| "unknown expo startup error".to_string())
        ));

        let has_next_attempt = index + 1 < attempts.len();
        if has_next_attempt {
            stop_session_command(session)?;
            thread::sleep(Duration::from_secs(1));
        }
    }

    Ok(ExpoStartupResult {
        success: false,
        tunnel_url: None,
        qr_code_value: None,
        web_url: None,
        startup_mode: None,
        warning: None,
        error: Some(errors.join("\n\n")),
    })
}

fn poll_expo_startup(
    session: &str,
    startup_mode: &str,
    require_tunnel_url: bool,
) -> Result<ExpoStartupResult> {
    let mut latest_output = String::new();

    for _ in 0..EXPO_STARTUP_ATTEMPTS {
        thread::sleep(EXPO_POLL_INTERVAL);

        let output = capture_session_output(session, 400)?;
        latest_output = output.clone();

        if let Some(error_context) = extract_error_context(&output) {
            return Ok(ExpoStartupResult {
                success: false,
                tunnel_url: None,
                qr_code_value: None,
                web_url: None,
                startup_mode: None,
                warning: None,
                error: Some(format!(
                    "Expo server failed to start in {startup_mode} mode:\n\n{}\n",
                    error_context
                )),
            });
        }

        let tunnel_url = extract_last_tunnel_url(&output);
        let web_url = extract_last_web_url(&output);
        let ready = is_expo_ready(&output);

        if require_tunnel_url {
            if tunnel_url.is_some() && ready {
                return Ok(ExpoStartupResult {
                    success: true,
                    tunnel_url: tunnel_url.clone(),
                    qr_code_value: tunnel_url,
                    web_url,
                    startup_mode: Some(startup_mode.to_string()),
                    warning: None,
                    error: None,
                });
            }
        } else if web_url.is_some() && (ready || output.contains("Starting Metro Bundler")) {
            return Ok(ExpoStartupResult {
                success: true,
                tunnel_url: None,
                qr_code_value: tunnel_url,
                web_url,
                startup_mode: Some(startup_mode.to_string()),
                warning: Some(
                    "Tunnel mode was unavailable, so Expo started in LAN mode. QR access works only from devices on the same network."
                        .to_string(),
                ),
                error: None,
            });
        }
    }

    Ok(ExpoStartupResult {
        success: false,
        tunnel_url: None,
        qr_code_value: None,
        web_url: None,
        startup_mode: None,
        warning: None,
        error: Some(format!(
            "Expo server failed to start in {startup_mode} mode. Terminal output:\n{}",
            last_chars(&latest_output, 1200)
        )),
    })
}

fn extract_last_tunnel_url(output: &str) -> Option<String> {
    extract_last_matching_token(output, |token| token.starts_with("exp://"))
}

fn extract_last_web_url(output: &str) -> Option<String> {
    extract_last_matching_token(output, |token| {
        (token.starts_with("http://") || token.starts_with("https://"))
            && (token.contains("localhost:")
                || token.contains("127.0.0.1:")
                || token.contains("://192.")
                || token.contains("://10.")
                || token.contains("://172."))
    })
}

fn extract_last_matching_token<F>(output: &str, predicate: F) -> Option<String>
where
    F: Fn(&str) -> bool,
{
    let mut last = None;
    for raw in output.split_whitespace() {
        let token = sanitize_url_token(raw);
        if predicate(token) {
            last = Some(token.to_string());
        }
    }
    last
}

fn sanitize_url_token(token: &str) -> &str {
    token.trim_matches(|c: char| matches!(c, ')' | ']' | '}' | ',' | ';' | '"' | '\''))
}

fn extract_error_context(output: &str) -> Option<String> {
    let lower = output.to_lowercase();
    for pattern in EXPO_ERROR_PATTERNS {
        if let Some(index) = lower.find(pattern) {
            let start = index.saturating_sub(100);
            let end = (index + 500).min(output.len());
            return Some(output[start..end].trim().to_string());
        }
    }
    None
}

fn is_expo_ready(output: &str) -> bool {
    EXPO_READY_MARKERS
        .iter()
        .any(|marker| output.contains(marker))
}

fn last_chars(value: &str, max_chars: usize) -> String {
    let chars: Vec<char> = value.chars().collect();
    let start = chars.len().saturating_sub(max_chars);
    chars[start..].iter().collect()
}

fn send_command_to_session(
    session: &str,
    run_dir: &str,
    env_file: Option<&Path>,
    command: &str,
) -> Result<()> {
    tmux(&["send-keys", "-t", session, "C-c"])?;
    thread::sleep(Duration::from_millis(150));
    tmux(&["send-keys", "-t", session, "clear", "C-m"])?;

    let run_dir_q = shell_quote(run_dir);
    let wrapped = if let Some(env_file) = env_file {
        let env_file_q = shell_quote(env_file.to_string_lossy().as_ref());
        format!(
            "cd {run_dir_q} && if [ -f {env_file_q} ]; then set -a; . {env_file_q}; set +a; fi; {command}"
        )
    } else {
        format!("cd {run_dir_q} && {command}")
    };

    tmux(&["send-keys", "-t", session, &wrapped, "C-m"])?;
    Ok(())
}

fn stop_session_command(session: &str) -> Result<()> {
    if session_exists(session)? {
        tmux(&["send-keys", "-t", session, "C-c"])?;
        thread::sleep(Duration::from_millis(250));
    }
    Ok(())
}

fn ensure_session(session: &str, run_dir: &Path) -> Result<()> {
    if !session_exists(session)? {
        let run_dir = run_dir.to_string_lossy().to_string();
        tmux(&["new-session", "-d", "-s", session, "-c", &run_dir])?;
    }
    Ok(())
}

fn session_exists(session: &str) -> Result<bool> {
    let status = Command::new("tmux")
        .args(["has-session", "-t", session])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .context("failed to execute tmux has-session")?;
    Ok(status.success())
}

fn capture_session_output(session: &str, lines: usize) -> Result<String> {
    let lines_arg = format!("-{}", lines.max(1));
    let output = Command::new("tmux")
        .args(["capture-pane", "-p", "-S", &lines_arg, "-t", session])
        .output()
        .context("failed to capture tmux pane output")?;

    if !output.status.success() {
        bail!(
            "tmux capture-pane failed for session {}: {}",
            session,
            String::from_utf8_lossy(&output.stderr)
        );
    }

    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

fn tmux(args: &[&str]) -> Result<()> {
    let output = Command::new("tmux")
        .args(args)
        .output()
        .with_context(|| format!("failed to execute tmux {:?}", args))?;

    if !output.status.success() {
        bail!(
            "tmux {:?} failed: {}",
            args,
            String::from_utf8_lossy(&output.stderr)
        );
    }

    Ok(())
}

fn run_shell_command(command: &str, run_dir: &Path) -> Result<()> {
    let status = Command::new("bash")
        .arg("-lc")
        .arg(command)
        .current_dir(run_dir)
        .stdin(Stdio::inherit())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .status()
        .with_context(|| format!("failed to start command `{command}`"))?;

    if !status.success() {
        bail!("command `{command}` failed in {}", run_dir.display());
    }
    Ok(())
}

fn run_command_capture(command: &mut Command, description: &str) -> Result<String> {
    let output = command
        .output()
        .with_context(|| format!("failed to execute {description}"))?;

    if !output.status.success() {
        let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
        let details = match (stdout.is_empty(), stderr.is_empty()) {
            (false, false) => format!("stdout:\n{stdout}\n\nstderr:\n{stderr}"),
            (false, true) => format!("stdout:\n{stdout}"),
            (true, false) => format!("stderr:\n{stderr}"),
            (true, true) => "no output".to_string(),
        };
        bail!("{description} failed: {details}");
    }

    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

fn copy_dir_recursive(src: &Path, dst: &Path) -> Result<()> {
    for entry in WalkDir::new(src) {
        let entry = entry.with_context(|| format!("failed to walk {}", src.display()))?;
        let rel = entry
            .path()
            .strip_prefix(src)
            .with_context(|| format!("failed to strip prefix {}", src.display()))?;
        let target = dst.join(rel);

        if entry.file_type().is_dir() {
            fs::create_dir_all(&target)
                .with_context(|| format!("failed to create {}", target.display()))?;
        } else if entry.file_type().is_file() {
            if let Some(parent) = target.parent() {
                fs::create_dir_all(parent)
                    .with_context(|| format!("failed to create {}", parent.display()))?;
            }
            fs::copy(entry.path(), &target).with_context(|| {
                format!(
                    "failed to copy {} to {}",
                    entry.path().display(),
                    target.display()
                )
            })?;
        } else {
            bail!("unsupported filesystem entry {}", entry.path().display());
        }
    }
    Ok(())
}

fn save_json_file<T: Serialize>(path: &Path, value: &T) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("failed to create {}", parent.display()))?;
    }
    let bytes = serde_json::to_vec_pretty(value).context("failed to serialize json")?;
    fs::write(path, bytes).with_context(|| format!("failed to write {}", path.display()))?;
    Ok(())
}

fn load_json_file<T: DeserializeOwned>(path: &Path) -> Result<T> {
    let bytes = fs::read(path).with_context(|| format!("failed to read {}", path.display()))?;
    serde_json::from_slice(&bytes).with_context(|| format!("invalid json {}", path.display()))
}

fn resolve_workspace_path(path: &Path, workspace: &Path) -> PathBuf {
    if path.is_absolute() {
        path.to_path_buf()
    } else {
        workspace.join(path)
    }
}

fn resolve_web_cache_path(cache_path: Option<&Path>, workspace: &Path) -> PathBuf {
    resolve_cache_path(cache_path, workspace, WEB_CACHE_FILE_NAME)
}

fn resolve_mobile_cache_path(cache_path: Option<&Path>, workspace: &Path) -> PathBuf {
    resolve_cache_path(cache_path, workspace, MOBILE_CACHE_FILE_NAME)
}

fn resolve_cache_path(cache_path: Option<&Path>, workspace: &Path, default_name: &str) -> PathBuf {
    match cache_path {
        Some(path) => {
            if path.is_absolute() {
                path.to_path_buf()
            } else {
                workspace.join(path)
            }
        }
        None => workspace.join(APP_CACHE_DIR_NAME).join(default_name),
    }
}

fn resolve_default_screenshot_dir(workspace: &Path) -> PathBuf {
    workspace.join(APP_CACHE_DIR_NAME).join(SCREENSHOT_DIR_NAME)
}

fn resolve_status_dir(output_dir: Option<&Path>, workspace: &Path) -> PathBuf {
    match output_dir {
        Some(path) => resolve_workspace_path(path, workspace),
        None => workspace.join(APP_CACHE_DIR_NAME).join(STATUS_DIR_NAME),
    }
}

fn resolve_screenshot_output_path(
    output: Option<&Path>,
    screenshot_dir: Option<&Path>,
    workspace: &Path,
    port: u16,
    screenshot_format: &str,
) -> Result<PathBuf> {
    let screenshot_dir = screenshot_dir.map(|path| resolve_workspace_path(path, workspace));
    let mut output_path = match output {
        Some(path) => {
            if path.is_absolute() {
                path.to_path_buf()
            } else if let Some(dir) = &screenshot_dir {
                dir.join(path)
            } else {
                workspace.join(path)
            }
        }
        None => {
            let dir = screenshot_dir.unwrap_or_else(|| resolve_default_screenshot_dir(workspace));
            let file_name = format!(
                "web-{}-{}.{}",
                port,
                unix_timestamp_seconds()?,
                screenshot_format
            );
            dir.join(file_name)
        }
    };

    output_path.set_extension(screenshot_format);
    Ok(output_path)
}

fn default_legacy_web_cache_path(workspace: &Path) -> PathBuf {
    workspace
        .join(LEGACY_WEB_CACHE_DIR_NAME)
        .join(LEGACY_WEB_CACHE_FILE_NAME)
}

fn discover_existing_web_cache_path(
    cache_path: Option<&Path>,
    workspace: &Path,
) -> Result<PathBuf> {
    let candidate = resolve_web_cache_path(cache_path, workspace);
    if candidate.exists() {
        return Ok(candidate);
    }

    if cache_path.is_none() {
        let legacy = default_legacy_web_cache_path(workspace);
        if legacy.exists() {
            return Ok(legacy);
        }
    }

    bail!(
        "web cache not found. Expected {}{}",
        candidate.display(),
        if cache_path.is_none() {
            format!(" or {}", default_legacy_web_cache_path(workspace).display())
        } else {
            String::new()
        }
    )
}

fn resolve_path(path: &Path) -> Result<PathBuf> {
    if path.is_absolute() {
        Ok(path.to_path_buf())
    } else {
        Ok(env::current_dir()
            .context("failed to read current directory")?
            .join(path))
    }
}

fn validate_preview_url(url: &str) -> Result<()> {
    if is_previewable_url(url) {
        return Ok(());
    }
    bail!("preview url is not browser-openable: {url}")
}

fn is_previewable_url(url: &str) -> bool {
    url.starts_with("http://") || url.starts_with("https://")
}

fn normalize_screenshot_format(format: &str) -> Result<&'static str> {
    match format.to_ascii_lowercase().as_str() {
        "png" => Ok("png"),
        "jpeg" | "jpg" => Ok("jpeg"),
        _ => bail!("unsupported screenshot format `{format}`. Allowed: png, jpeg"),
    }
}

fn resolve_existing_directory(candidate: &Path, workspace: &Path) -> Result<PathBuf> {
    let path = resolve_workspace_path(candidate, workspace);
    if !path.is_dir() {
        bail!("project directory does not exist: {}", path.display());
    }
    Ok(path)
}

fn validate_https_url(url: &str, label: &str) -> Result<()> {
    if url.starts_with("https://") {
        return Ok(());
    }
    bail!("{label} must start with https://")
}

fn validate_stripe_secret_key(secret_key: &str) -> Result<()> {
    if secret_key.starts_with("sk_live_") || secret_key.starts_with("sk_test_") {
        return Ok(());
    }
    bail!("invalid stripe_secret_key format. Must start with sk_live_ or sk_test_")
}

fn normalize_stripe_events(events: &[String]) -> Vec<String> {
    let normalized: Vec<String> = events
        .iter()
        .map(|event| event.trim())
        .filter(|event| !event.is_empty())
        .map(|event| event.to_string())
        .collect();
    if normalized.is_empty() {
        DEFAULT_STRIPE_EVENTS
            .iter()
            .map(|event| event.to_string())
            .collect()
    } else {
        normalized
    }
}

fn generate_stripe_idempotency_key(endpoint_url: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(endpoint_url.as_bytes());
    let hex = format!("{:x}", hasher.finalize());
    format!("webhook_register_{}", &hex[..32])
}

fn register_stripe_webhook(
    stripe_secret_key: &str,
    endpoint_url: &str,
    events: &[String],
    description: &str,
    idempotency_key: &str,
) -> Result<StripeWebhookApiResponse> {
    let client = Client::builder()
        .timeout(Duration::from_secs(DEFAULT_STRIPE_TIMEOUT_SECONDS))
        .build()
        .context("failed to construct Stripe HTTP client")?;

    let mut form_fields = vec![
        ("url".to_string(), endpoint_url.to_string()),
        ("description".to_string(), description.to_string()),
    ];
    for event in events {
        form_fields.push(("enabled_events[]".to_string(), event.clone()));
    }

    let response = client
        .post("https://api.stripe.com/v1/webhook_endpoints")
        .bearer_auth(stripe_secret_key)
        .header("Idempotency-Key", idempotency_key)
        .form(&form_fields)
        .send()
        .context("failed to call Stripe API")?;

    let status = response.status();
    let body = response
        .text()
        .context("failed to read Stripe API response body")?;

    if status.is_success() {
        return serde_json::from_str::<StripeWebhookApiResponse>(&body)
            .context("failed to parse Stripe webhook response");
    }

    let error_message = extract_stripe_error_message(&body);
    match status.as_u16() {
        400 => bail!("bad request: {error_message}"),
        401 => bail!("invalid Stripe API key. Please check STRIPE_SECRET_KEY."),
        409 => bail!("a webhook with this endpoint URL may already exist (idempotency conflict)"),
        _ => bail!(
            "Stripe API error (status {}): {error_message}",
            status.as_u16()
        ),
    }
}

fn extract_stripe_error_message(body: &str) -> String {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .and_then(|value| {
            value
                .get("error")
                .and_then(|error| error.get("message"))
                .and_then(|message| message.as_str())
                .map(ToString::to_string)
        })
        .unwrap_or_else(|| body.trim().to_string())
}

fn write_env_key(path: &Path, key: &str, value: &str, export_format: bool) -> Result<()> {
    let existing_lines: Vec<String> = if path.exists() {
        fs::read_to_string(path)
            .with_context(|| format!("failed to read {}", path.display()))?
            .lines()
            .map(ToString::to_string)
            .collect()
    } else {
        Vec::new()
    };

    let line_prefix = if export_format {
        format!("export {key}=")
    } else {
        format!("{key}=")
    };
    let new_value = if export_format {
        format!("export {key}={}", shell_quote(value))
    } else {
        format!("{key}={value}")
    };

    let mut updated = false;
    let mut new_lines = Vec::with_capacity(existing_lines.len() + 1);
    for line in existing_lines {
        let stripped = line.trim();
        if stripped.starts_with(&line_prefix)
            || stripped.starts_with(&format!("{key}="))
            || stripped.starts_with(&format!("{key} ="))
        {
            new_lines.push(new_value.clone());
            updated = true;
        } else {
            new_lines.push(line);
        }
    }

    if !updated {
        new_lines.push(new_value);
    }

    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("failed to create {}", parent.display()))?;
    }
    fs::write(path, format!("{}\n", new_lines.join("\n")))
        .with_context(|| format!("failed to write {}", path.display()))?;
    Ok(())
}

fn validate_project_name(project_name: &str) -> Result<()> {
    if project_name.is_empty() {
        bail!("project name cannot be empty");
    }
    if project_name.contains('/') || project_name.contains('\\') || project_name.contains("..") {
        bail!("project name must not contain path separators or ..");
    }
    if !project_name
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
    {
        bail!("project name must contain only ascii letters, digits, - or _");
    }
    Ok(())
}

fn validate_mobile_template(template: &str) -> Result<()> {
    if MOBILE_TEMPLATES.iter().any(|item| item == &template) {
        return Ok(());
    }
    bail!(
        "unsupported mobile template `{template}`. Allowed: {}",
        MOBILE_TEMPLATES.join(", ")
    )
}

fn get_template_spec(template_id: &str) -> Result<TemplateSpec> {
    TEMPLATE_SPECS
        .iter()
        .copied()
        .find(|spec| spec.id == template_id)
        .ok_or_else(|| anyhow!("unknown template_id `{template_id}`"))
}

fn discover_skill_root() -> Result<PathBuf> {
    if let Ok(root) = env::var("II_APP_SKILL_ROOT") {
        let path = PathBuf::from(root);
        if path.join("assets").join("templates").is_dir() {
            return Ok(path);
        }
    }

    if let Ok(root) = env::var("II_WEB_SERVER_SKILL_ROOT") {
        let path = PathBuf::from(root);
        if path.join("assets").join("templates").is_dir() {
            return Ok(path);
        }
    }

    if let Ok(exe) = env::current_exe() {
        if let Some(parent) = exe.parent() {
            for candidate in parent.ancestors() {
                if candidate.join("assets").join("templates").is_dir() {
                    return Ok(candidate.to_path_buf());
                }
            }
        }
    }

    if let Ok(cwd) = env::current_dir() {
        for candidate in cwd.ancestors() {
            if candidate.join("assets").join("templates").is_dir() {
                return Ok(candidate.to_path_buf());
            }
        }
    }

    bail!("could not discover skill root containing assets/templates")
}

fn run_agent_browser_screenshot(
    url: &str,
    output_path: &Path,
    annotate: bool,
    screenshot_format: &str,
    screenshot_quality: Option<u8>,
) -> Result<()> {
    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("failed to create {}", parent.display()))?;
    }

    if let Some(quality) = screenshot_quality {
        if screenshot_format != "jpeg" {
            bail!("--screenshot-quality requires --screenshot-format jpeg");
        }
        if quality > 100 {
            bail!("--screenshot-quality must be between 0 and 100");
        }
    }

    let output_path_str = output_path.to_string_lossy().to_string();

    run_command_capture(
        Command::new("agent-browser").args(["open", url]),
        "agent-browser open",
    )?;

    let screenshot_result = (|| -> Result<()> {
        let mut command = Command::new("agent-browser");
        command
            .arg("screenshot")
            .arg("--screenshot-format")
            .arg(screenshot_format);
        if annotate {
            command.arg("--annotate");
        }
        if let Some(quality) = screenshot_quality {
            command.arg("--screenshot-quality").arg(quality.to_string());
        }
        command.arg(&output_path_str);
        run_command_capture(&mut command, "agent-browser screenshot")?;
        Ok(())
    })();

    let close_result = run_command_capture(
        Command::new("agent-browser").arg("close"),
        "agent-browser close",
    );
    if let Err(err) = screenshot_result {
        let _ = close_result;
        return Err(err);
    }
    close_result?;

    if !output_path.is_file() {
        bail!(
            "agent-browser reported success but screenshot was not found at {}",
            output_path.display()
        );
    }

    Ok(())
}

fn find_available_port(start_port: u16) -> Result<u16> {
    for port in start_port..u16::MAX {
        if TcpListener::bind(("127.0.0.1", port)).is_ok() {
            return Ok(port);
        }
    }
    bail!("no available port found starting at {}", start_port)
}

fn wait_for_port(port: u16, timeout: Duration) -> Result<()> {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if TcpListener::bind(("127.0.0.1", port)).is_err() {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(250));
    }
    bail!("port {} did not become active in time", port)
}

fn deployment_url(port: u16, host_url: Option<&str>) -> String {
    if let Some(host_url) = host_url {
        return format!("https://{port}-{host_url}");
    }
    format!("http://127.0.0.1:{port}")
}

fn extract_host_url(preview_url: &str) -> Option<String> {
    let host = preview_url.strip_prefix("https://")?;
    let host = host.split('/').next()?;
    let (prefix, suffix) = host.split_once('-')?;
    if prefix.parse::<u16>().is_ok() {
        Some(suffix.to_string())
    } else {
        None
    }
}

fn default_web_session(config: &DeploymentConfig) -> String {
    config
        .servers
        .iter()
        .find(|server| server.port == config.preview_port)
        .or_else(|| config.servers.first())
        .map(|server| server.session.clone())
        .unwrap_or_else(|| "unknown-session".to_string())
}

fn join_suffix(base: &Path, suffix: &str) -> PathBuf {
    if suffix.is_empty() {
        base.to_path_buf()
    } else {
        base.join(suffix)
    }
}

fn web_session_name(project_name: &str, role: &str) -> String {
    format!(
        "ii-app-web-{}-{}",
        sanitize_session_fragment(project_name),
        sanitize_session_fragment(role)
    )
}

fn mobile_session_name(project_name: &str) -> String {
    format!("ii-app-mobile-{}", sanitize_session_fragment(project_name))
}

fn sanitize_session_fragment(value: &str) -> String {
    value
        .chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '-' || c == '_' {
                c
            } else {
                '-'
            }
        })
        .collect()
}

fn unix_timestamp_seconds() -> Result<u64> {
    Ok(SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .context("system clock is before unix epoch")?
        .as_secs())
}

fn shell_quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\"'\"'"))
}

fn print_json<T: Serialize>(value: &T) -> Result<()> {
    println!(
        "{}",
        serde_json::to_string_pretty(value).context("failed to render json")?
    );
    Ok(())
}
