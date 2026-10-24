//! Authenticated local command transport and bounded daemon execution.

use crate::{config::Runtime, output};
use anyhow::{bail, ensure, Context, Result};
use fs2::FileExt;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    ffi::OsString,
    fs::{File, OpenOptions},
    io::{Read, Seek, SeekFrom, Write},
    net::{Ipv4Addr, SocketAddr, SocketAddrV4, TcpListener, TcpStream},
    path::{Path, PathBuf},
    sync::{mpsc, Arc, Mutex},
    thread,
    time::{Duration, Instant},
};

const PROTOCOL: u32 = 1;
const MAX_REQUEST: usize = 1024 * 1024;
const HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(3);

#[derive(Serialize, Deserialize)]
pub(crate) struct Request {
    pub args: Vec<OsString>,
    pub cwd: PathBuf,
    pub terminal: String,
    pub cfg: Runtime,
    pub telemetry_enabled: bool,
}

#[derive(Serialize, Deserialize)]
struct Endpoint {
    protocol: u32,
    #[serde(default)]
    version: String,
    port: u16,
    token: String,
    pid: u32,
}

#[derive(Serialize, Deserialize)]
struct Hello {
    protocol: u32,
    token: String,
    operation: Operation,
}

#[derive(Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
enum Operation {
    Probe,
    Execute(Request),
    Stop,
}

fn private_file(path: &Path) -> Result<File> {
    let mut options = OpenOptions::new();
    options.read(true).write(true).create(true).truncate(false);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    Ok(options.open(path)?)
}

fn write_json(writer: &mut impl Write, value: &impl Serialize) -> Result<()> {
    let bytes = serde_json::to_vec(value)?;
    ensure!(
        bytes.len() <= MAX_REQUEST,
        "daemon command metadata exceeds limit"
    );
    writer.write_all(&(bytes.len() as u32).to_be_bytes())?;
    writer.write_all(&bytes)?;
    writer.flush()?;
    Ok(())
}

fn read_json<T: for<'a> Deserialize<'a>>(reader: &mut impl Read) -> Result<T> {
    let mut length = [0; 4];
    reader.read_exact(&mut length)?;
    let length = u32::from_be_bytes(length) as usize;
    ensure!(
        length <= MAX_REQUEST,
        "daemon command metadata exceeds limit"
    );
    let mut bytes = vec![0; length];
    reader.read_exact(&mut bytes)?;
    Ok(serde_json::from_slice(&bytes)?)
}

fn endpoint(cfg: &Runtime) -> Result<Endpoint> {
    let bytes = std::fs::read(cfg.home.join("daemon.json"))?;
    ensure!(bytes.len() <= 4096, "invalid daemon endpoint");
    let endpoint: Endpoint = serde_json::from_slice(&bytes)?;
    ensure!(
        endpoint.protocol == PROTOCOL,
        "daemon protocol mismatch; restart amail daemon"
    );
    ensure!(
        endpoint.token.len() == 72,
        "invalid daemon authentication state"
    );
    Ok(endpoint)
}

fn connect(endpoint: &Endpoint) -> Result<TcpStream> {
    let address = SocketAddr::V4(SocketAddrV4::new(Ipv4Addr::LOCALHOST, endpoint.port));
    let stream = TcpStream::connect_timeout(&address, HANDSHAKE_TIMEOUT)?;
    stream.set_nodelay(true)?;
    stream.set_read_timeout(Some(HANDSHAKE_TIMEOUT))?;
    stream.set_write_timeout(Some(HANDSHAKE_TIMEOUT))?;
    Ok(stream)
}

fn send_hello(stream: &mut TcpStream, endpoint: &Endpoint, operation: Operation) -> Result<()> {
    write_json(
        stream,
        &Hello {
            protocol: PROTOCOL,
            token: endpoint.token.clone(),
            operation,
        },
    )?;
    let mut ack = [0];
    stream.read_exact(&mut ack)?;
    if ack == [2] {
        bail!("amail daemon is busy; command was not executed");
    }
    ensure!(ack == [1], "daemon rejected command authentication");
    Ok(())
}

fn probe(cfg: &Runtime) -> Result<Endpoint> {
    let endpoint = endpoint(cfg)?;
    let mut stream = connect(&endpoint)?;
    send_hello(&mut stream, &endpoint, Operation::Probe)?;
    Ok(endpoint)
}

#[cfg(not(windows))]
fn spawn(cfg: &Runtime) -> Result<()> {
    let mut command = std::process::Command::new(std::env::current_exe()?);
    command
        .arg("_daemon")
        .env("AMAIL_HOME", &cfg.home)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null());
    command.spawn().context("starting amail daemon")?;
    Ok(())
}

#[cfg(windows)]
fn spawn(_cfg: &Runtime) -> Result<()> {
    use std::{
        os::windows::{
            ffi::OsStrExt,
            io::{FromRawHandle, OwnedHandle},
        },
        ptr,
    };
    use windows_sys::Win32::System::Threading::{
        CreateProcessW, CREATE_NO_WINDOW, PROCESS_INFORMATION, STARTUPINFOW,
    };
    let executable: Vec<u16> = std::env::current_exe()?
        .as_os_str()
        .encode_wide()
        .chain(Some(0))
        .collect();
    let mut arguments: Vec<u16> = "amail _daemon\0".encode_utf16().collect();
    let startup = STARTUPINFOW {
        cb: std::mem::size_of::<STARTUPINFOW>() as u32,
        ..Default::default()
    };
    let mut process = PROCESS_INFORMATION::default();
    // Stable Rust's launcher inherits every marked handle, including ancestor
    // capture pipes that are not current stdio. Inherit no handles at all.
    // https://github.com/rust-lang/rust/blob/1.98.1/library/std/src/sys/process/windows.rs#L310-L343
    let created = unsafe {
        CreateProcessW(
            executable.as_ptr(),
            arguments.as_mut_ptr(),
            ptr::null(),
            ptr::null(),
            0,
            CREATE_NO_WINDOW,
            ptr::null(),
            ptr::null(),
            &startup,
            &mut process,
        )
    };
    if created == 0 {
        return Err(std::io::Error::last_os_error()).context("starting amail daemon");
    }
    // Environment and cwd are inherited; Runtime::load already resolved this
    // process's AMAIL_HOME. Closing our handles does not terminate the daemon.
    let _process = unsafe { OwnedHandle::from_raw_handle(process.hProcess) };
    let _thread = unsafe { OwnedHandle::from_raw_handle(process.hThread) };
    Ok(())
}
fn ensure_running(cfg: &Runtime) -> Result<Endpoint> {
    if let Ok(endpoint) = probe(cfg) {
        return Ok(endpoint);
    }
    let lock = private_file(&cfg.home.join("daemon-start.lock"))?;
    lock.lock_exclusive()?;
    if let Ok(endpoint) = probe(cfg) {
        return Ok(endpoint);
    }
    spawn(cfg)?;
    let start = Instant::now();
    let budget = Duration::from_secs(cfg.daemon.start_timeout_seconds.clamp(1, 120));
    while start.elapsed() < budget {
        if let Ok(endpoint) = probe(cfg) {
            return Ok(endpoint);
        }
        thread::sleep(Duration::from_millis(50));
    }
    bail!("amail daemon did not become ready; inspect configuration or restart the daemon")
}

/// No command is replayed after dispatch. A disconnected result may be unknown.
pub(crate) fn forward(cfg: &Runtime, args: Vec<OsString>) -> Result<i32> {
    let endpoint = ensure_running(cfg)?;
    ensure!(
        endpoint.version == env!("CARGO_PKG_VERSION"),
        "amail daemon version differs from this client; run `amail daemon stop` before upgrading"
    );
    let request = Request {
        args,
        cwd: std::env::current_dir()?,
        terminal: terminal_id(cfg)?,
        cfg: cfg.clone(),
        telemetry_enabled: crate::telemetry::enabled(),
    };
    let mut stream = connect(&endpoint)?;
    send_hello(&mut stream, &endpoint, Operation::Execute(request))?;
    stream.set_read_timeout(None)?;
    stream.set_write_timeout(None)?;
    output::consume(&mut stream)
}

pub(crate) fn status(cfg: &Runtime) -> Result<serde_json::Value> {
    match probe(cfg) {
        Ok(endpoint) => Ok(
            serde_json::json!({"running":true,"pid":endpoint.pid,"protocol":endpoint.protocol,"version":endpoint.version}),
        ),
        Err(_) => Ok(serde_json::json!({"running":false})),
    }
}

pub(crate) fn stop(cfg: &Runtime) -> Result<()> {
    let endpoint = probe(cfg).context("no authenticated amail daemon is running")?;
    let mut stream = connect(&endpoint)?;
    send_hello(&mut stream, &endpoint, Operation::Stop)?;
    drop(stream);
    let singleton = private_file(&cfg.home.join("daemon.lock"))?;
    let deadline =
        Instant::now() + Duration::from_secs(cfg.daemon.start_timeout_seconds.clamp(1, 120));
    while Instant::now() < deadline {
        if singleton.try_lock_exclusive().is_ok() {
            return Ok(());
        }
        // A replacement endpoint can only be published after this daemon's
        // singleton was released. Do not wait for an unrelated replacement.
        if self::endpoint(cfg).is_ok_and(|current| current.token != endpoint.token) {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(25));
    }
    bail!("amail daemon is stopping; previously accepted operations are still finishing")
}

fn authenticate(expected: &str, actual: &str) -> bool {
    if expected.len() != actual.len() {
        return false;
    }
    expected
        .bytes()
        .zip(actual.bytes())
        .fold(0_u8, |difference, (a, b)| difference | (a ^ b))
        == 0
}

fn handle(stream: TcpStream, request: Request) {
    output::install(stream);
    let result =
        std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| crate::run_daemon(request)));
    let code = match result {
        Ok(Ok(())) => 0,
        Ok(Err(error)) => {
            if crate::machine::enabled() {
                crate::machine::event("error", crate::machine::error_record(&error));
            } else {
                output::err(format_args!("amail: {error}"));
            }
            1
        }
        Err(_) => {
            output::err(format_args!(
                "amail: daemon operation failed unexpectedly; mutation outcome may be unknown"
            ));
            1
        }
    };
    let _ = output::finish(code);
}

type Work = (TcpStream, Request, mpsc::Receiver<()>);

fn start_workers(capacity: usize) -> (mpsc::SyncSender<Work>, Vec<thread::JoinHandle<()>>) {
    let (sender, receiver) = mpsc::sync_channel::<Work>(capacity);
    let receiver = Arc::new(Mutex::new(receiver));
    let workers: Vec<_> = (0..capacity)
        .map(|_| {
            let receiver = receiver.clone();
            thread::spawn(move || loop {
                let work = receiver.lock().expect("daemon queue lock poisoned").recv();
                let Ok((stream, request, ready)) = work else {
                    break;
                };
                if ready.recv().is_ok() {
                    handle(stream, request);
                }
            })
        })
        .collect();
    (sender, workers)
}

fn start_sweeper(cfg: Runtime) -> (mpsc::Sender<()>, thread::JoinHandle<()>) {
    let (stop, stopped) = mpsc::channel();
    let worker = thread::spawn(move || loop {
        let _ = crate::daemon_tick(&cfg);
        if stopped.recv_timeout(Duration::from_secs(30)) != Err(mpsc::RecvTimeoutError::Timeout) {
            break;
        }
    });
    (stop, worker)
}

fn enqueue(
    stream: &mut TcpStream,
    request: Request,
    sender: &mpsc::SyncSender<Work>,
) -> Result<()> {
    stream.set_read_timeout(None)?;
    stream.set_write_timeout(None)?;
    // Acknowledgment precedes the only execution boundary. Busy queues reject
    // before acknowledgment and never silently replay a mutation.
    let (ready, admission) = mpsc::channel();
    if sender
        .try_send((stream.try_clone()?, request, admission))
        .is_err()
    {
        stream.write_all(&[2])?;
        return Ok(());
    }
    stream.write_all(&[1])?;
    let _ = ready.send(());
    Ok(())
}

fn admit(
    mut stream: TcpStream,
    endpoint: &Endpoint,
    home: &Path,
    sender: &mpsc::SyncSender<Work>,
) -> Result<bool> {
    stream.set_read_timeout(Some(HANDSHAKE_TIMEOUT))?;
    stream.set_write_timeout(Some(HANDSHAKE_TIMEOUT))?;
    let hello: Hello = read_json(&mut stream)?;
    if hello.protocol != PROTOCOL || !authenticate(&endpoint.token, &hello.token) {
        stream.write_all(&[0])?;
        return Ok(false);
    }
    match hello.operation {
        Operation::Probe => stream.write_all(&[1])?,
        Operation::Stop => {
            stream.write_all(&[1])?;
            return Ok(true);
        }
        Operation::Execute(request) if request.cfg.home == home => {
            enqueue(&mut stream, request, sender)?
        }
        Operation::Execute(_) => stream.write_all(&[0])?,
    }
    Ok(false)
}

/// The singleton lock owns the endpoint, listener, worker pool, and expiry sweep.
pub(crate) fn serve(cfg: &Runtime) -> Result<()> {
    let singleton = private_file(&cfg.home.join("daemon.lock"))?;
    singleton
        .try_lock_exclusive()
        .context("amail daemon is already running")?;
    // Establish schema/WAL before the sweeper and first request can contend on
    // a fresh database's journal-mode transition.
    drop(crate::profiles::Store::open(cfg)?);
    let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0))?;
    let endpoint = Endpoint {
        protocol: PROTOCOL,
        version: env!("CARGO_PKG_VERSION").to_owned(),
        port: listener.local_addr()?.port(),
        token: format!("{}{}", uuid::Uuid::new_v4(), uuid::Uuid::new_v4()),
        pid: std::process::id(),
    };
    publish_endpoint(cfg, &endpoint)?;
    let (sender, workers) = start_workers(cfg.daemon.max_concurrency.clamp(1, 64));
    let (stop_sweeper, sweeper) = start_sweeper(cfg.clone());
    let outcome = loop {
        match listener.accept() {
            Ok((stream, address)) => {
                if !address.ip().is_loopback() {
                    continue;
                }
                if admit(stream, &endpoint, &cfg.home, &sender).unwrap_or(false) {
                    break Ok(());
                }
            }
            Err(error) if error.kind() == std::io::ErrorKind::Interrupted => continue,
            Err(error) => break Err(error.into()),
        }
    };
    drop(listener);
    let _ = stop_sweeper.send(());
    if self::endpoint(cfg).is_ok_and(|current| current.token == endpoint.token) {
        let _ = std::fs::remove_file(cfg.home.join("daemon.json"));
    }
    drop(sender);
    for worker in workers {
        let _ = worker.join();
    }
    let _ = sweeper.join();
    outcome
}

fn publish_endpoint(cfg: &Runtime, endpoint: &Endpoint) -> Result<()> {
    let path = cfg.home.join("daemon.json");
    let staging = cfg
        .home
        .join(format!("daemon-{}.json", uuid::Uuid::new_v4()));
    let mut file = private_file(&staging)?;
    file.write_all(&serde_json::to_vec(endpoint)?)?;
    file.sync_all()?;
    // The singleton lock makes removing a predecessor safe on Windows, whose
    // rename does not replace an existing destination.
    if path.exists() {
        std::fs::remove_file(&path)?;
    }
    std::fs::rename(staging, path)?;
    Ok(())
}

fn terminal_fingerprint() -> Result<String> {
    if let Some(explicit) = std::env::var_os("AMAIL_TERMINAL_ID") {
        ensure!(!explicit.is_empty(), "AMAIL_TERMINAL_ID must not be empty");
        return Ok(format!("explicit:{explicit:?}"));
    }
    let pane = std::env::var("TMUX_PANE").unwrap_or_default();
    #[cfg(unix)]
    {
        let session = unsafe { libc::getsid(0) };
        ensure!(session >= 0, "cannot determine terminal session");
        return Ok(format!("unix:{session}:{pane}"));
    }
    #[cfg(windows)]
    {
        let window = unsafe { windows_sys::Win32::System::Console::GetConsoleWindow() };
        let session = std::env::var("WT_SESSION").unwrap_or_default();
        ensure!(
            !window.is_null() || !session.is_empty(),
            "cannot identify this terminal; set a stable AMAIL_TERMINAL_ID"
        );
        return Ok(format!("windows:{window:p}:{session}:{pane}"));
    }
    #[allow(unreachable_code)]
    {
        bail!("terminal identity unavailable; set AMAIL_TERMINAL_ID")
    }
}

/// OS terminal coordinates never become cloud capabilities. A private random
/// token remains stable across processes in the same terminal session instead.
pub(crate) fn terminal_id(cfg: &Runtime) -> Result<String> {
    let fingerprint = terminal_fingerprint()?;
    let digest = Sha256::digest(fingerprint.as_bytes());
    let name: String = digest.iter().map(|byte| format!("{byte:02x}")).collect();
    let directory = cfg.home.join("terminals");
    std::fs::create_dir_all(&directory)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&directory, std::fs::Permissions::from_mode(0o700))?;
    }
    let mut file = private_file(&directory.join(name))?;
    file.lock_exclusive()?;
    let mut token = String::new();
    file.read_to_string(&mut token)?;
    if token.is_empty() {
        token = uuid::Uuid::new_v4().to_string();
        file.seek(SeekFrom::Start(0))?;
        file.write_all(token.as_bytes())?;
        file.sync_all()?;
    }
    uuid::Uuid::parse_str(&token).context("invalid private terminal identity")?;
    Ok(token)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicBool, Ordering};

    fn config(home: &Path) -> Runtime {
        Runtime {
            api_base: "https://mail.moesegfault.dev".into(),
            issuer: "https://identity.moesegfault.dev".into(),
            client_id: "amail-cli".into(),
            redirect_uri: "http://127.0.0.1/callback".into(),
            home: home.to_owned(),
            yolo: false,
            daemon: crate::config::DaemonConfig::default(),
        }
    }

    #[test]
    fn authentication_requires_the_whole_secret() {
        assert!(authenticate("abc", "abc"));
        assert!(!authenticate("abc", "abd"));
        assert!(!authenticate("abc", "ab"));
        assert!(!authenticate("abc", ""));
    }

    #[test]
    fn metadata_is_bounded_before_allocation() {
        let bytes = ((MAX_REQUEST + 1) as u32).to_be_bytes();
        assert!(read_json::<Hello>(&mut std::io::Cursor::new(bytes)).is_err());
    }

    #[test]
    fn metadata_rejects_truncation() {
        assert!(read_json::<Hello>(&mut std::io::Cursor::new([0, 0, 0, 5, b'{'])).is_err());
    }

    #[test]
    fn stop_waits_for_singleton_not_just_endpoint_removal() {
        let home = tempfile::tempdir().unwrap();
        let cfg = config(home.path());
        let child_cfg = cfg.clone();
        let drained = Arc::new(AtomicBool::new(false));
        let child_drained = drained.clone();
        let (ready, admission) = mpsc::channel();
        let server = thread::spawn(move || {
            let singleton = private_file(&child_cfg.home.join("daemon.lock")).unwrap();
            singleton.lock_exclusive().unwrap();
            let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
            let endpoint = Endpoint {
                protocol: PROTOCOL,
                version: env!("CARGO_PKG_VERSION").into(),
                port: listener.local_addr().unwrap().port(),
                token: format!("{}{}", uuid::Uuid::new_v4(), uuid::Uuid::new_v4()),
                pid: std::process::id(),
            };
            publish_endpoint(&child_cfg, &endpoint).unwrap();
            ready.send(()).unwrap();
            for expected_stop in [false, true] {
                let (mut stream, _) = listener.accept().unwrap();
                let hello: Hello = read_json(&mut stream).unwrap();
                assert_eq!(matches!(hello.operation, Operation::Stop), expected_stop);
                stream.write_all(&[1]).unwrap();
            }
            std::fs::remove_file(child_cfg.home.join("daemon.json")).unwrap();
            thread::sleep(Duration::from_millis(100));
            child_drained.store(true, Ordering::SeqCst);
            drop(singleton);
        });
        admission.recv().unwrap();
        stop(&cfg).unwrap();
        assert!(drained.load(Ordering::SeqCst));
        server.join().unwrap();
    }
}
