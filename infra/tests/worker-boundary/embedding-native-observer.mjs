/** Test-only observer of native APIs, scoped to the single synthetic OpenRouter exchange. */
import RustWorker from "../../../crates/mail-worker/build/worker/shim.mjs";

const endpoint = "https://openrouter.ai/api/v1/embeddings";
const streams = new WeakSet();
const readers = new WeakSet();
const signals = new WeakSet();
const stats = { exchanges: 0, reads: 0, bytes: 0, lateReads: 0,
  cancelCalls: 0, cancelFulfilled: 0, cancelRejected: 0, abortCalls: 0, abortedSignals: 0 };
const nativeFetch = globalThis.fetch;
globalThis.fetch = async function(input, init) {
  const url = typeof input === "string" ? input : input.url;
  if (url !== endpoint) return nativeFetch.call(this, input, init);
  stats.exchanges++;
  if (init?.signal) signals.add(init.signal);
  const response = await nativeFetch.call(this, input, init);
  if (response.body) streams.add(response.body);
  return response;
};

const nativeGetReader = ReadableStream.prototype.getReader;
ReadableStream.prototype.getReader = function(...args) {
  const reader = nativeGetReader.apply(this, args);
  if (streams.has(this)) readers.add(reader);
  return reader;
};
const probe = new ReadableStream().getReader();
const readerPrototype = Object.getPrototypeOf(probe);
probe.releaseLock();
const nativeRead = readerPrototype.read;
readerPrototype.read = async function(...args) {
  if (!readers.has(this)) return nativeRead.apply(this, args);
  stats.reads++;
  if (stats.bytes > 65_536 || stats.cancelCalls > 0) stats.lateReads++;
  const result = await nativeRead.apply(this, args);
  if (!result.done) stats.bytes += result.value.byteLength;
  return result;
};
const nativeCancel = readerPrototype.cancel;
readerPrototype.cancel = async function(...args) {
  if (!readers.has(this)) return nativeCancel.apply(this, args);
  stats.cancelCalls++;
  try {
    const result = await nativeCancel.apply(this, args);
    stats.cancelFulfilled++;
    return result;
  } catch (error) {
    stats.cancelRejected++;
    throw error;
  }
};
const nativeAbort = AbortController.prototype.abort;
AbortController.prototype.abort = function(...args) {
  const tracked = signals.has(this.signal);
  if (tracked) stats.abortCalls++;
  const result = nativeAbort.apply(this, args);
  if (tracked && this.signal.aborted) stats.abortedSignals++;
  return result;
};

/** Subclass the generated WorkerEntrypoint, retaining its environment and context. */
export default class EmbeddingNativeObserver extends RustWorker {
  async fetch(request) {
    const response = await super.fetch(request);
    const headers = new Headers(response.headers);
    for (const [name, value] of Object.entries(stats)) {
      headers.set(`x-synthetic-native-${name.toLowerCase()}`, String(value));
    }
    return new Response(response.body, { status: response.status, headers });
  }
}
