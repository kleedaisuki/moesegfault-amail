//! Per-request streaming output. Mail payloads never travel through this channel.

use anyhow::{Context, Result};
use std::{
    cell::RefCell,
    fmt,
    io::{self, Read, Write},
    net::TcpStream,
};

pub(crate) const STDOUT: u8 = 1;
pub(crate) const STDERR: u8 = 2;
pub(crate) const EXIT: u8 = 3;
const CHUNK: usize = 64 * 1024;

thread_local! {
    static STREAM: RefCell<Option<TcpStream>> = const { RefCell::new(None) };
    static FAILED: RefCell<Option<io::Error>> = const { RefCell::new(None) };
}

pub(crate) fn frame(writer: &mut impl Write, channel: u8, bytes: &[u8]) -> io::Result<()> {
    for chunk in bytes.chunks(CHUNK) {
        writer.write_all(&[channel])?;
        writer.write_all(&(chunk.len() as u32).to_be_bytes())?;
        writer.write_all(chunk)?;
    }
    writer.flush()
}

pub(crate) fn install(stream: TcpStream) {
    STREAM.with(|current| *current.borrow_mut() = Some(stream));
    FAILED.with(|current| *current.borrow_mut() = None);
}

pub(crate) fn finish(code: i32) -> Result<()> {
    let failure = FAILED.with(|current| current.borrow_mut().take());
    let stream = STREAM.with(|current| current.borrow_mut().take());
    if let Some(mut stream) = stream {
        frame(&mut stream, EXIT, &code.to_be_bytes())?;
    }
    if let Some(error) = failure {
        return Err(error).context("client output disconnected");
    }
    Ok(())
}

fn line(channel: u8, args: fmt::Arguments<'_>) {
    let text = format!("{args}\n");
    let result = STREAM.with(|current| match current.borrow_mut().as_mut() {
        Some(stream) => frame(stream, channel, text.as_bytes()),
        None if channel == STDOUT => io::stdout().lock().write_all(text.as_bytes()),
        None => io::stderr().lock().write_all(text.as_bytes()),
    });
    if let Err(error) = result {
        FAILED.with(|current| {
            let mut current = current.borrow_mut();
            if current.is_none() {
                *current = Some(error);
            }
        });
    }
}

pub(crate) fn out(args: fmt::Arguments<'_>) {
    line(STDOUT, args);
}

pub(crate) fn err(args: fmt::Arguments<'_>) {
    line(STDERR, args);
}

/// Stream bounded frames directly to the client's inherited output handles.
pub(crate) fn consume(reader: &mut impl Read) -> Result<i32> {
    let mut buffer = [0_u8; CHUNK];
    loop {
        let mut header = [0_u8; 5];
        reader
            .read_exact(&mut header)
            .context("daemon disconnected; operation outcome may be unknown")?;
        let size = u32::from_be_bytes(header[1..].try_into().unwrap()) as usize;
        anyhow::ensure!(size <= CHUNK, "invalid daemon output frame");
        reader.read_exact(&mut buffer[..size])?;
        match header[0] {
            STDOUT => {
                let mut output = io::stdout().lock();
                output.write_all(&buffer[..size])?;
                output.flush()?;
            }
            STDERR => {
                let mut output = io::stderr().lock();
                output.write_all(&buffer[..size])?;
                output.flush()?;
            }
            EXIT if size == 4 => return Ok(i32::from_be_bytes(buffer[..4].try_into().unwrap())),
            _ => anyhow::bail!("invalid daemon output channel"),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn frames_are_bounded_and_preserve_exact_bytes() {
        let bytes = vec![b'x'; CHUNK * 2 + 7];
        let mut wire = Vec::new();
        frame(&mut wire, STDOUT, &bytes).unwrap();
        let mut restored = Vec::new();
        let mut cursor = io::Cursor::new(wire);
        while cursor.position() < cursor.get_ref().len() as u64 {
            let mut header = [0; 5];
            cursor.read_exact(&mut header).unwrap();
            assert_eq!(header[0], STDOUT);
            let length = u32::from_be_bytes(header[1..].try_into().unwrap()) as usize;
            assert!(length <= CHUNK);
            let mut chunk = vec![0; length];
            cursor.read_exact(&mut chunk).unwrap();
            restored.extend(chunk);
        }
        assert_eq!(restored, bytes);
    }

    #[test]
    fn rejects_oversized_frames_before_allocation() {
        let mut wire = vec![STDOUT];
        wire.extend_from_slice(&((CHUNK + 1) as u32).to_be_bytes());
        assert!(consume(&mut io::Cursor::new(wire)).is_err());
    }

    #[test]
    fn concurrent_requests_keep_output_and_exit_status_separate() {
        use std::{net::TcpListener, thread};
        let mut requests = Vec::new();
        for number in 0_i32..4 {
            let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
            let client = TcpStream::connect(listener.local_addr().unwrap()).unwrap();
            let (server, _) = listener.accept().unwrap();
            let worker = thread::spawn(move || {
                install(server);
                out(format_args!("request-{number}"));
                err(format_args!("diagnostic-{number}"));
                finish(number).unwrap();
            });
            requests.push((number, client, worker));
        }
        for (number, mut stream, worker) in requests {
            for (channel, expected) in [
                (STDOUT, format!("request-{number}\n")),
                (STDERR, format!("diagnostic-{number}\n")),
                (EXIT, String::new()),
            ] {
                let mut header = [0; 5];
                stream.read_exact(&mut header).unwrap();
                assert_eq!(header[0], channel);
                let size = u32::from_be_bytes(header[1..].try_into().unwrap()) as usize;
                let mut bytes = vec![0; size];
                stream.read_exact(&mut bytes).unwrap();
                if channel == EXIT {
                    assert_eq!(bytes, number.to_be_bytes());
                } else {
                    assert_eq!(bytes, expected.as_bytes());
                }
            }
            worker.join().unwrap();
        }
    }
}
