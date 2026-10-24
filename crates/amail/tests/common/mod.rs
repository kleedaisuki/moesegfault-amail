//! Private native-CLI fixtures, never a bypass for interactive approval tests.

use std::{
    io::{self, Read},
    path::Path,
    process::{Command, Output, Stdio},
    thread,
    time::{Duration, Instant},
};

pub struct Fixture {
    home: tempfile::TempDir,
}

impl Fixture {
    pub fn new() -> Self {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.temp");
        std::fs::create_dir_all(&root).unwrap();
        let home = tempfile::tempdir_in(root).unwrap();
        std::fs::write(home.path().join("config.toml"), "yolo = true\n").unwrap();
        Self { home }
    }

    pub fn path(&self) -> &Path {
        self.home.path()
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        if self.path().join("daemon.json").exists() {
            let _ = bounded_output(
                command(self.path())
                    .args(["daemon", "stop"])
                    .env("AMAIL_TELEMETRY", "off"),
            );
        }
    }
}

pub fn command(home: &Path) -> Command {
    let mut command = Command::new(env!("CARGO_BIN_EXE_amail"));
    command
        .env("AMAIL_HOME", home)
        .env(
            "AMAIL_TERMINAL_ID",
            format!(
                "integration-{}",
                home.file_name().unwrap().to_string_lossy()
            ),
        )
        .env("AMAIL_API_BASE", "https://mail.example.test")
        .env("AMAIL_ISSUER", "https://identity.example.test")
        .env("AMAIL_CLIENT_ID", "")
        .env("AMAIL_REDIRECT_URI", "");
    command
}

pub fn output(command: &mut Command) -> Output {
    bounded_output(command).expect("offline CLI command must finish within 15 seconds")
}

fn bounded_output(command: &mut Command) -> io::Result<Output> {
    let mut child = command
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?;
    let mut stdout = child.stdout.take().unwrap();
    let mut stderr = child.stderr.take().unwrap();
    let out = thread::spawn(move || {
        let mut bytes = Vec::new();
        stdout.read_to_end(&mut bytes).map(|_| bytes)
    });
    let err = thread::spawn(move || {
        let mut bytes = Vec::new();
        stderr.read_to_end(&mut bytes).map(|_| bytes)
    });
    let deadline = Instant::now() + Duration::from_secs(15);
    let status = loop {
        if let Some(status) = child.try_wait()? {
            break status;
        }
        if Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "offline CLI command exceeded 15 seconds",
            ));
        }
        thread::sleep(Duration::from_millis(10));
    };
    Ok(Output {
        status,
        stdout: out.join().unwrap()?,
        stderr: err.join().unwrap()?,
    })
}
