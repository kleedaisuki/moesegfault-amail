# Encrypt confidential stdin in memory; never print exception details.
param([ValidateSet('encrypt','synthetic')][string]$Mode = 'encrypt')
$ErrorActionPreference = 'Stop'
try {
    if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'unsupported' }
    Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Security.Cryptography;

/// <summary>One-shot bounded envelope; no plaintext filesystem operations.</summary>
public static class PrivateProviderCrypto {
    public const int RecordSize = 262144;
    /// <summary>Require canonical SPKI RSA-3072 and supported authenticated crypto.</summary>
    public static RSA PublicKey(string encoded) {
        if (!AesGcm.IsSupported || encoded.Length > 2048) throw new Exception();
        byte[] der = Convert.FromBase64String(encoded);
        if (Convert.ToBase64String(der) != encoded) throw new Exception();
        RSA rsa = RSA.Create();
        try {
            rsa.ImportSubjectPublicKeyInfo(der, out int count);
            if (count != der.Length || rsa.KeySize != 3072 ||
                !CryptographicOperations.FixedTimeEquals(der, rsa.ExportSubjectPublicKeyInfo()))
                throw new Exception();
            return rsa;
        } catch { rsa.Dispose(); throw; }
    }
    /// <summary>Frame one projection, encrypt it, and return only ciphertext JSON.</summary>
    public static string Encrypt(byte[] projection, string publicKey, string metadata) {
        if (projection.Length == 0 || projection.Length > 131072) throw new Exception();
        using RSA rsa = PublicKey(publicKey);
        using JsonDocument meta = JsonDocument.Parse(metadata);
        byte[] key = RandomNumberGenerator.GetBytes(32);
        byte[] nonce = RandomNumberGenerator.GetBytes(12);
        byte[] frame = new byte[RecordSize];
        byte[] cipher = new byte[RecordSize];
        byte[] tag = new byte[16];
        try {
            System.Buffers.Binary.BinaryPrimitives.WriteInt32BigEndian(frame, projection.Length);
            projection.CopyTo(frame, 4);
            byte[] header = JsonSerializer.SerializeToUtf8Bytes(new {
                algorithm = "RSA-3072-OAEP-SHA256+A256GCM", fingerprint =
                    Convert.ToHexString(SHA256.HashData(rsa.ExportSubjectPublicKeyInfo())).ToLowerInvariant(),
                nonce = Convert.ToBase64String(nonce), wrapped_key =
                    Convert.ToBase64String(rsa.Encrypt(key, RSAEncryptionPadding.OaepSHA256)),
                provenance = meta.RootElement
            });
            using AesGcm aes = new AesGcm(key, 16);
            aes.Encrypt(nonce, frame, cipher, tag, header);
            return JsonSerializer.Serialize(new { version = 1, header = Convert.ToBase64String(header),
                ciphertext = Convert.ToBase64String(cipher), tag = Convert.ToBase64String(tag) });
        } finally {
            CryptographicOperations.ZeroMemory(key);
            CryptographicOperations.ZeroMemory(frame);
            CryptographicOperations.ZeroMemory(projection);
        }
    }
    /// <summary>Synthetic in-memory interoperation and tamper checks; no operator key.</summary>
    public static void Synthetic() {
        using RSA rsa = RSA.Create(3072);
        string pub = Convert.ToBase64String(rsa.ExportSubjectPublicKeyInfo());
        byte[] expected = Encoding.UTF8.GetBytes("{\"http_status\":200,\"errors\":[{\"message\":\"synthetic\\nsecret\"}]}");
        string envelope = Encrypt((byte[])expected.Clone(), pub, "{\"synthetic\":true}");
        using JsonDocument outer = JsonDocument.Parse(envelope);
        byte[] header = Convert.FromBase64String(outer.RootElement.GetProperty("header").GetString());
        using JsonDocument parsed = JsonDocument.Parse(header);
        byte[] key = rsa.Decrypt(Convert.FromBase64String(parsed.RootElement.GetProperty("wrapped_key").GetString()), RSAEncryptionPadding.OaepSHA256);
        byte[] nonce = Convert.FromBase64String(parsed.RootElement.GetProperty("nonce").GetString());
        byte[] cipher = Convert.FromBase64String(outer.RootElement.GetProperty("ciphertext").GetString());
        byte[] tag = Convert.FromBase64String(outer.RootElement.GetProperty("tag").GetString());
        byte[] frame = new byte[RecordSize];
        try {
            using AesGcm aes = new AesGcm(key,16);
            aes.Decrypt(nonce, cipher, tag, frame, header);
            int length = System.Buffers.Binary.BinaryPrimitives.ReadInt32BigEndian(frame);
            if (length != expected.Length || !CryptographicOperations.FixedTimeEquals(expected, frame.AsSpan(4,length))) throw new Exception();
            foreach (byte[] component in new [] { nonce, cipher, tag, header }) {
                component[0] ^= 1;
                bool rejected = false;
                try { aes.Decrypt(nonce,cipher,tag,frame,header); } catch (CryptographicException) { rejected = true; }
                component[0] ^= 1;
                if (!rejected) throw new Exception();
            }
            using RSA other = RSA.Create(3072);
            bool wrongKey = false;
            try { other.Decrypt(Convert.FromBase64String(parsed.RootElement.GetProperty("wrapped_key").GetString()),RSAEncryptionPadding.OaepSHA256); }
            catch (CryptographicException) { wrongKey = true; }
            if (!wrongKey) throw new Exception();
        } finally { CryptographicOperations.ZeroMemory(key); CryptographicOperations.ZeroMemory(frame); }
    }
}
'@
    if ($Mode -eq 'synthetic') {
        [PrivateProviderCrypto]::Synthetic()
        Write-Output 'private_capture_crypto=PASS'
        exit 0
    }
    $inputStream = [Console]::OpenStandardInput()
    $memory = [IO.MemoryStream]::new()
    $buffer = [byte[]]::new(4096)
    while (($count = $inputStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
        if ($memory.Length + $count -gt 131072) { throw 'bounded' }
        $memory.Write($buffer, 0, $count)
    }
    $ciphertext = [PrivateProviderCrypto]::Encrypt($memory.ToArray(), $env:PRIVATE_CAPTURE_PUBLIC_KEY, $env:PRIVATE_CAPTURE_METADATA)
    # Ciphertext is returned over the pipe, not written before parent validation.
    [Console]::Out.Write($ciphertext)
    [Security.Cryptography.CryptographicOperations]::ZeroMemory($buffer)
    [Security.Cryptography.CryptographicOperations]::ZeroMemory($memory.GetBuffer())
    $memory.Dispose()
    exit 0
} catch {
    # No arbitrary exceptions, provider prose, keys, paths or input on stderr.
    exit 1
}
