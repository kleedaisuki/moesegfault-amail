# Encrypt confidential stdin in memory; never print exception details.
param([ValidateSet('encrypt','synthetic','keygen','classify')][string]$Mode = 'encrypt', [string]$Session = '')
$ErrorActionPreference = 'Stop'
try {
    if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'unsupported' }
    Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Security.Cryptography;
using System.Diagnostics;

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
    public static void Synthetic(RSA supplied = null, string captured = null) {
        using RSA generated = supplied == null ? RSA.Create(3072) : null;
        RSA rsa = supplied ?? generated;
        string pub = Convert.ToBase64String(rsa.ExportSubjectPublicKeyInfo());
        byte[] expected = Encoding.UTF8.GetBytes("{\"http_status\":200,\"errors\":[{\"message\":\"synthetic\\nsecret\"}]}");
        string envelope = captured ?? Encrypt((byte[])expected.Clone(), pub, "{\"synthetic\":true}");
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
    /// <summary>Exercise Python validation and the actual anonymous-stdin child boundary.</summary>
    public static void Boundary(string script) {
        using RSA rsa = RSA.Create(3072);
        ProcessStartInfo start = new ProcessStartInfo("python") {
            UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true
        };
        start.ArgumentList.Add(script);
        start.ArgumentList.Add("synthetic-boundary");
        var inherited = new System.Collections.Generic.Dictionary<string,string>();
        foreach (string name in new [] {"PATH","SystemRoot","HOME","TMPDIR","TEMP","TMP","DOTNET_ROOT"})
            if (Environment.GetEnvironmentVariable(name) is string value) inherited[name] = value;
        start.Environment.Clear();
        foreach (var pair in inherited) start.Environment[pair.Key] = pair.Value;
        start.Environment["PRIVATE_CAPTURE_SYNTHETIC_HOSTED"] = "1";
        start.Environment["PRIVATE_CAPTURE_PUBLIC_KEY"] = Convert.ToBase64String(rsa.ExportSubjectPublicKeyInfo());
        start.Environment["PYTHONDONTWRITEBYTECODE"] = "1";
        using Process process = Process.Start(start);
        string output = process.StandardOutput.ReadToEnd();
        string errors = process.StandardError.ReadToEnd();
        if (!process.WaitForExit(60000) || process.ExitCode != 0 || errors.Length != 0 ||
            output.Length > 400000 || output.Contains("synthetic\\nsecret")) throw new Exception();
        Synthetic(rsa, output);
    }
    /// <summary>Decrypt authenticated bytes in memory and emit only public error classes.</summary>
    public static string Classify(byte[] envelope, byte[] privateKey) {
        using RSA rsa = RSA.Create();
        byte[] key = null;
        byte[] frame = new byte[RecordSize];
        try {
            rsa.ImportPkcs8PrivateKey(privateKey, out int count);
            if (count != privateKey.Length || rsa.KeySize != 3072) throw new Exception();
            using JsonDocument outer = JsonDocument.Parse(envelope);
            byte[] header = Convert.FromBase64String(outer.RootElement.GetProperty("header").GetString());
            using JsonDocument parsed = JsonDocument.Parse(header);
            if (parsed.RootElement.GetProperty("fingerprint").GetString() !=
                Convert.ToHexString(SHA256.HashData(rsa.ExportSubjectPublicKeyInfo())).ToLowerInvariant()) throw new Exception();
            key = rsa.Decrypt(Convert.FromBase64String(parsed.RootElement.GetProperty("wrapped_key").GetString()), RSAEncryptionPadding.OaepSHA256);
            using AesGcm aes = new AesGcm(key,16);
            aes.Decrypt(Convert.FromBase64String(parsed.RootElement.GetProperty("nonce").GetString()),
                Convert.FromBase64String(outer.RootElement.GetProperty("ciphertext").GetString()),
                Convert.FromBase64String(outer.RootElement.GetProperty("tag").GetString()),frame,header);
            int length = System.Buffers.Binary.BinaryPrimitives.ReadInt32BigEndian(frame);
            if (length < 1 || length > 131072) throw new Exception();
            for (int i = length + 4; i < frame.Length; i++) if (frame[i] != 0) throw new Exception();
            using JsonDocument payload = JsonDocument.Parse(frame.AsMemory(4,length));
            if (payload.RootElement.ValueKind != JsonValueKind.Object) throw new Exception();
            int fields = 0;
            foreach (var field in payload.RootElement.EnumerateObject()) {
                if (field.Name != "http_status" && field.Name != "errors") throw new Exception();
                fields++;
            }
            if (fields != 2 || !payload.RootElement.GetProperty("http_status").TryGetInt32(out int status)) throw new Exception();
            JsonElement errors = payload.RootElement.GetProperty("errors");
            if (errors.ValueKind != JsonValueKind.Array || errors.GetArrayLength() == 0) return "unclassified";
            var classes = new System.Collections.Generic.HashSet<string>();
            foreach (JsonElement error in errors.EnumerateArray()) {
                string category = "unclassified";
                if (error.ValueKind == JsonValueKind.Object && error.TryGetProperty("message", out JsonElement message) && message.ValueKind == JsonValueKind.String) {
                    string text = message.GetString();
                    if (text.Length <= 2048) {
                        if (text == "Unauthorized") category = "authentication";
                        else if (text == "not authorized for that account") category = "authorization_or_dataset_access";
                        else if (System.Text.RegularExpressions.Regex.IsMatch(text, "\\Aunknown field[^\\r\\n]{0,512}\\z")) category = "schema_or_field";
                        else if (System.Text.RegularExpressions.Regex.IsMatch(text, "\\Aerror parsing args[^\\r\\n]{0,512}\\z")) category = "arguments_or_filter";
                        else if (text == "Internal server error") category = "internal";
                    }
                }
                classes.Add(category);
            }
            return classes.Count == 1 ? System.Linq.Enumerable.First(classes) : "mixed";
        } finally {
            CryptographicOperations.ZeroMemory(privateKey);
            if (key != null) CryptographicOperations.ZeroMemory(key);
            CryptographicOperations.ZeroMemory(frame);
        }
    }
}
'@
    if ($Mode -eq 'synthetic') {
        [PrivateProviderCrypto]::Synthetic()
        [PrivateProviderCrypto]::Boundary((Join-Path $PSScriptRoot 'private_provider_capture.py'))
        Write-Output 'private_capture_crypto=PASS'
        exit 0
    }
    if ($Mode -in @('keygen','classify')) {
        # Private keys are local-only. Hosted synthetic mode never uses this branch.
        if ($env:GITHUB_ACTIONS -eq 'true' -or $Session -notmatch '\A[a-z0-9-]{1,40}\z') { throw 'scope' }
        $root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
        $base = Join-Path $root '.temp/private-provider-diag'
        $folder = Join-Path $base $Session
        foreach ($path in @((Join-Path $root '.temp'), $base, $folder)) {
            if ((Test-Path -LiteralPath $path) -and ((Get-Item -Force -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'scope' }
        }
        $keyPath = Join-Path $folder 'private.pk8'
        if ($Mode -eq 'keygen') {
            if (Test-Path -LiteralPath $folder) { throw 'exists' }
            [IO.Directory]::CreateDirectory($folder) | Out-Null
            if ($IsWindows) {
                $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
                $acl = [Security.AccessControl.DirectorySecurity]::new()
                $acl.SetOwner($sid)
                $acl.SetAccessRuleProtection($true,$false)
                $rule = [Security.AccessControl.FileSystemAccessRule]::new($sid,'FullControl','ContainerInherit,ObjectInherit','None','Allow')
                $acl.AddAccessRule($rule)
                Set-Acl -LiteralPath $folder -AclObject $acl
            } else {
                [IO.File]::SetUnixFileMode($folder, [IO.UnixFileMode]448)
            }
            $rsa = [Security.Cryptography.RSA]::Create(3072)
            $private = $rsa.ExportPkcs8PrivateKey()
            try {
                $options = [IO.FileStreamOptions]::new()
                $options.Mode = [IO.FileMode]::CreateNew
                $options.Access = [IO.FileAccess]::Write
                $options.Share = [IO.FileShare]::None
                if (-not $IsWindows) { $options.UnixCreateMode = [IO.UnixFileMode]384 }
                $stream = [IO.FileStream]::new($keyPath,$options)
                try { $stream.Write($private) } finally { $stream.Dispose() }
                if (-not $IsWindows) { [IO.File]::SetUnixFileMode($keyPath,[IO.UnixFileMode]384) }
                [IO.File]::WriteAllText((Join-Path $folder 'public.spki'),[Convert]::ToBase64String($rsa.ExportSubjectPublicKeyInfo()))
                [IO.File]::WriteAllText((Join-Path $folder 'created.utc'),[DateTimeOffset]::UtcNow.ToString('O'))
            } finally { [Security.Cryptography.CryptographicOperations]::ZeroMemory($private); $rsa.Dispose() }
            Write-Output 'private_provider_key=GENERATED'
            exit 0
        }
        foreach ($path in @($folder,$keyPath)) {
            if (-not (Test-Path -LiteralPath $path) -or ((Get-Item -Force -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'scope' }
            if ($IsWindows) {
                $acl = Get-Acl -LiteralPath $path
                $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
                foreach ($entry in $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])) {
                    if ($entry.IdentityReference.Value -ne $sid -or $entry.AccessControlType -ne 'Allow') { throw 'acl' }
                }
                if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $sid) { throw 'acl' }
            } elseif (([int][IO.File]::GetUnixFileMode($path) -band 63) -ne 0) { throw 'acl' }
        }
        if ((Get-Item -LiteralPath $keyPath).Length -gt 4096) { throw 'bounded' }
        $raw = [IO.MemoryStream]::new()
        $stdin = [Console]::OpenStandardInput()
        $block = [byte[]]::new(4096)
        while (($count = $stdin.Read($block,0,$block.Length)) -gt 0) {
            if ($raw.Length + $count -gt 400000) { throw 'bounded' }
            $raw.Write($block,0,$count)
        }
        $category = [PrivateProviderCrypto]::Classify($raw.ToArray(),[IO.File]::ReadAllBytes($keyPath))
        [Console]::Out.Write($category)
        $raw.Dispose()
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
