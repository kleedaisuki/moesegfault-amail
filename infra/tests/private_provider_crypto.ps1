# Encrypt confidential stdin in memory; never print exception details.
param([ValidateSet('encrypt','synthetic','keygen','classify','classify-offline')][string]$Mode = 'encrypt', [string]$Session = '')
$ErrorActionPreference = 'Stop'

# Reject NULL/absent DACLs and every raw ACE not owned by this user. A NULL
# DACL has zero enumerable access rules but grants everyone access.
function Test-OwnerOnlyAcl($Acl, [string]$Sid, [bool]$RequireProtected) {
    $raw = [Security.AccessControl.RawSecurityDescriptor]::new($Acl.GetSecurityDescriptorBinaryForm(),0)
    if (-not ($raw.ControlFlags -band [Security.AccessControl.ControlFlags]::DiscretionaryAclPresent) -or
        $null -eq $raw.DiscretionaryAcl -or $raw.DiscretionaryAcl.Count -lt 1 -or
        $raw.Owner.Value -ne $Sid -or ($RequireProtected -and -not $Acl.AreAccessRulesProtected)) { return $false }
    foreach ($ace in $raw.DiscretionaryAcl) {
        if ($ace -isnot [Security.AccessControl.CommonAce] -or
            $ace.IsCallback -or $ace.AceQualifier -ne [Security.AccessControl.AceQualifier]::AccessAllowed -or
            $ace.SecurityIdentifier.Value -ne $Sid) { return $false }
    }
    return $true
}
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
        if (Classify(Encoding.UTF8.GetBytes(envelope), rsa.ExportPkcs8PrivateKey()) != "unclassified")
            throw new Exception();
        if (Classify(Encoding.UTF8.GetBytes(envelope), rsa.ExportPkcs8PrivateKey(), true) != "http=ok errors=unclassified")
            throw new Exception();
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
    /// <summary>Frozen public templates from staging_worker_r2_history_error.py, reviewed offline only.</summary>
    private static readonly (string Category, string Pattern)[] OfflineTemplates = {
        ("authentication", @"Unauthorized"),
        ("authorization_or_dataset_access", @"not authorized for that account"),
        ("authorization_or_dataset_access", @"zones \[[^\r\n]{0,512}\] are not authorized"),
        ("authorization_or_dataset_access", @"does not have access to the path[^\r\n]{0,512}"),
        ("schema_or_field", @"unknown field[^\r\n]{0,512}"),
        ("schema_or_field", @"scalar fields must have no selections"),
        ("schema_or_field", @"object field must have selections"),
        ("arguments_or_filter", @"error parsing args[^\r\n]{0,512}"),
        ("query_invalid", @"query contains error, please review it and retry"),
        ("dataset_limit", @"cannot request data older than[^\r\n]{0,512}"),
        ("dataset_limit", @"number of fields can't be more than[^\r\n]{0,512}"),
        ("dataset_limit", @"limit must be positive number and not greater than[^\r\n]{0,512}"),
        ("dataset_limit", @"query time range is too large[^\r\n]{0,512}"),
        ("rate_or_resource", @"rate limiter budget depleted, try again after 5 minutes"),
        ("rate_or_resource", @"in combination, your request queries too many nodes, zones and accounts"),
        ("rate_or_resource", @"query consumed excessive resources, please try running smaller queries which consume fewer resources"),
        ("service_unavailable", @"unable to execute query, please try again later"),
        ("service_unavailable", @"too many queries in progress, please try again later"),
        ("internal", @"Internal server error"),
    };
    /// <summary>Reject duplicate keys recursively, including uninterpreted private siblings.</summary>
    private static void Unique(JsonElement value) {
        if (value.ValueKind == JsonValueKind.Object) {
            var names = new System.Collections.Generic.HashSet<string>(StringComparer.Ordinal);
            foreach (var field in value.EnumerateObject()) {
                if (!names.Add(field.Name)) throw new Exception();
                Unique(field.Value);
            }
        } else if (value.ValueKind == JsonValueKind.Array) {
            foreach (var item in value.EnumerateArray()) Unique(item);
        }
    }
    /// <summary>Serialize only fixed HTTP bins; status is not a diagnosis of GraphQL cause.</summary>
    private static string HttpBin(int status) {
        switch (status) {
            case 200: return "ok";
            case 401: return "authentication";
            case 403: return "forbidden";
            case 400: return "bad_request";
            case 429: return "rate_limited";
            default: return status >= 500 ? "server_error" : "other";
        }
    }
    /// <summary>Use UTF-16 code-unit bounds and ordinal full matches, never truncate private text.</summary>
    private static string ErrorBin(JsonElement error) {
        if (error.ValueKind != JsonValueKind.Object ||
            !error.TryGetProperty("message", out JsonElement message) ||
            message.ValueKind != JsonValueKind.String) return "invalid";
        string text = message.GetString();
        if (text.Length > 2048) return "invalid";
        var classes = new System.Collections.Generic.HashSet<string>(StringComparer.Ordinal);
        foreach (var template in OfflineTemplates) {
            if (System.Text.RegularExpressions.Regex.IsMatch(text, @"\A(?:" + template.Pattern + @")\z",
                System.Text.RegularExpressions.RegexOptions.CultureInvariant,
                TimeSpan.FromMilliseconds(100))) classes.Add(template.Category);
        }
        if (error.TryGetProperty("extensions", out JsonElement extensions) &&
            extensions.ValueKind == JsonValueKind.Object &&
            extensions.TryGetProperty("code", out JsonElement code) &&
            code.ValueKind == JsonValueKind.String &&
            String.Equals(code.GetString(), "budget", StringComparison.Ordinal)) classes.Add("rate_or_resource");
        return classes.Count == 0 ? "unclassified" : classes.Count == 1 ?
            System.Linq.Enumerable.First(classes) : "mixed";
    }
    /// <summary>Offline bounded declassification; malformed JSON/status fails closed, malformed errors are invalid.</summary>
    public static string Interpret(ReadOnlyMemory<byte> projection) {
        if (projection.Length < 1 || projection.Length > 131072) throw new Exception();
        using JsonDocument payload = JsonDocument.Parse(projection, new JsonDocumentOptions { MaxDepth = 64 });
        JsonElement root = payload.RootElement;
        Unique(root);
        if (root.ValueKind != JsonValueKind.Object) throw new Exception();
        int fields = 0;
        foreach (var field in root.EnumerateObject()) {
            if (field.Name != "http_status" && field.Name != "errors") throw new Exception();
            fields++;
        }
        if (fields != 2 || !root.TryGetProperty("http_status", out JsonElement http) ||
            http.ValueKind != JsonValueKind.Number || !http.TryGetInt32(out int status) ||
            status < 100 || status > 599) throw new Exception();
        JsonElement errors = root.GetProperty("errors");
        string category = "invalid";
        if (errors.ValueKind == JsonValueKind.Array && errors.GetArrayLength() >= 1 && errors.GetArrayLength() <= 8) {
            var classes = new System.Collections.Generic.HashSet<string>(StringComparer.Ordinal);
            foreach (var error in errors.EnumerateArray()) {
                string entry = ErrorBin(error);
                // Invalid structure overrides partial recognition across the entire array.
                if (entry == "invalid") return "http=" + HttpBin(status) + " errors=invalid";
                classes.Add(entry);
            }
            category = classes.Count == 1 ? System.Linq.Enumerable.First(classes) : "mixed";
        }
        return "http=" + HttpBin(status) + " errors=" + category;
    }
    /// <summary>Synthetic-only classifier boundary matrix; no keys, sessions, files or network.</summary>
    public static void SyntheticOffline() {
        var cases = new (string Projection, string Expected)[] {
            (@"{""http_status"": 200, ""errors"": [{""message"": ""Unauthorized""}]}", @"http=ok errors=authentication"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""prefixUnauthorized""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""Unauthorized\n""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""Unauthorized\r""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""uNAUTHORIZED""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""Unauthorizedsuffix""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""not authorized for that account""}]}", @"http=ok errors=authorization_or_dataset_access"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""prefixnot authorized for that account""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""not authorized for that account\n""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""not authorized for that account\r""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""NOT AUTHORIZED FOR THAT ACCOUNT""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""not authorized for that accountsuffix""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""zones [PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id] are not authorized""}]}", @"http=ok errors=authorization_or_dataset_access"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""prefixzones [PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id] are not authorized""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""zones [PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id] are not authorized\n""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""zones [PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id] are not authorized\r""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""ZONES [private-hostile HTTPS://EVIL.INVALID/ token ACCOUNT-ID] ARE NOT AUTHORIZED""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""does not have access to the pathPRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=ok errors=authorization_or_dataset_access"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""prefixdoes not have access to the pathPRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""does not have access to the pathPRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id\n""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""does not have access to the pathPRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id\r""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""DOES NOT HAVE ACCESS TO THE PATHprivate-hostile HTTPS://EVIL.INVALID/ token ACCOUNT-ID""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""unknown fieldPRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=ok errors=schema_or_field"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""prefixunknown fieldPRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""unknown fieldPRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id\n""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""unknown fieldPRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id\r""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""UNKNOWN FIELDprivate-hostile HTTPS://EVIL.INVALID/ token ACCOUNT-ID""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""scalar fields must have no selections""}]}", @"http=ok errors=schema_or_field"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""prefixscalar fields must have no selections""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""scalar fields must have no selections\n""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""scalar fields must have no selections\r""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""SCALAR FIELDS MUST HAVE NO SELECTIONS""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""scalar fields must have no selectionssuffix""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""object field must have selections""}]}", @"http=ok errors=schema_or_field"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""prefixobject field must have selections""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""object field must have selections\n""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""object field must have selections\r""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""OBJECT FIELD MUST HAVE SELECTIONS""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""object field must have selectionssuffix""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""error parsing argsPRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=ok errors=arguments_or_filter"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""prefixerror parsing argsPRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""error parsing argsPRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id\n""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""error parsing argsPRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id\r""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""ERROR PARSING ARGSprivate-hostile HTTPS://EVIL.INVALID/ token ACCOUNT-ID""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""query contains error, please review it and retry""}]}", @"http=ok errors=query_invalid"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""prefixquery contains error, please review it and retry""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""query contains error, please review it and retry\n""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""query contains error, please review it and retry\r""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""QUERY CONTAINS ERROR, PLEASE REVIEW IT AND RETRY""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""query contains error, please review it and retrysuffix""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""cannot request data older thanPRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=ok errors=dataset_limit"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""prefixcannot request data older thanPRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""cannot request data older thanPRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id\n""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""cannot request data older thanPRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id\r""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""CANNOT REQUEST DATA OLDER THANprivate-hostile HTTPS://EVIL.INVALID/ token ACCOUNT-ID""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""number of fields can't be more thanPRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=ok errors=dataset_limit"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""prefixnumber of fields can't be more thanPRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""number of fields can't be more thanPRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id\n""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""number of fields can't be more thanPRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id\r""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""NUMBER OF FIELDS CAN'T BE MORE THANprivate-hostile HTTPS://EVIL.INVALID/ token ACCOUNT-ID""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""limit must be positive number and not greater thanPRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=ok errors=dataset_limit"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""prefixlimit must be positive number and not greater thanPRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""limit must be positive number and not greater thanPRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id\n""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""limit must be positive number and not greater thanPRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id\r""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""LIMIT MUST BE POSITIVE NUMBER AND NOT GREATER THANprivate-hostile HTTPS://EVIL.INVALID/ token ACCOUNT-ID""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""query time range is too largePRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=ok errors=dataset_limit"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""prefixquery time range is too largePRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""query time range is too largePRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id\n""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""query time range is too largePRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id\r""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""QUERY TIME RANGE IS TOO LARGEprivate-hostile HTTPS://EVIL.INVALID/ token ACCOUNT-ID""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""rate limiter budget depleted, try again after 5 minutes""}]}", @"http=ok errors=rate_or_resource"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""prefixrate limiter budget depleted, try again after 5 minutes""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""rate limiter budget depleted, try again after 5 minutes\n""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""rate limiter budget depleted, try again after 5 minutes\r""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""RATE LIMITER BUDGET DEPLETED, TRY AGAIN AFTER 5 MINUTES""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""rate limiter budget depleted, try again after 5 minutessuffix""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""in combination, your request queries too many nodes, zones and accounts""}]}", @"http=ok errors=rate_or_resource"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""prefixin combination, your request queries too many nodes, zones and accounts""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""in combination, your request queries too many nodes, zones and accounts\n""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""in combination, your request queries too many nodes, zones and accounts\r""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""IN COMBINATION, YOUR REQUEST QUERIES TOO MANY NODES, ZONES AND ACCOUNTS""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""in combination, your request queries too many nodes, zones and accountssuffix""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""query consumed excessive resources, please try running smaller queries which consume fewer resources""}]}", @"http=ok errors=rate_or_resource"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""prefixquery consumed excessive resources, please try running smaller queries which consume fewer resources""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""query consumed excessive resources, please try running smaller queries which consume fewer resources\n""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""query consumed excessive resources, please try running smaller queries which consume fewer resources\r""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""QUERY CONSUMED EXCESSIVE RESOURCES, PLEASE TRY RUNNING SMALLER QUERIES WHICH CONSUME FEWER RESOURCES""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""query consumed excessive resources, please try running smaller queries which consume fewer resourcessuffix""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""unable to execute query, please try again later""}]}", @"http=ok errors=service_unavailable"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""prefixunable to execute query, please try again later""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""unable to execute query, please try again later\n""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""unable to execute query, please try again later\r""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""UNABLE TO EXECUTE QUERY, PLEASE TRY AGAIN LATER""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""unable to execute query, please try again latersuffix""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""too many queries in progress, please try again later""}]}", @"http=ok errors=service_unavailable"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""prefixtoo many queries in progress, please try again later""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""too many queries in progress, please try again later\n""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""too many queries in progress, please try again later\r""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""TOO MANY QUERIES IN PROGRESS, PLEASE TRY AGAIN LATER""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""too many queries in progress, please try again latersuffix""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""Internal server error""}]}", @"http=ok errors=internal"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""prefixInternal server error""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""Internal server error\n""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""Internal server error\r""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""iNTERNAL SERVER ERROR""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""Internal server errorsuffix""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""unknown fieldxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx""}]}", @"http=ok errors=schema_or_field"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""unknown fieldxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx""}]}", @"http=ok errors=invalid"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00""}]}", @"http=ok errors=invalid"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""\u96ea""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 100, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=other errors=unclassified"),
            (@"{""http_status"": 201, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=other errors=unclassified"),
            (@"{""http_status"": 499, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=other errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 401, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=authentication errors=unclassified"),
            (@"{""http_status"": 403, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=forbidden errors=unclassified"),
            (@"{""http_status"": 400, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=bad_request errors=unclassified"),
            (@"{""http_status"": 429, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=rate_limited errors=unclassified"),
            (@"{""http_status"": 500, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=server_error errors=unclassified"),
            (@"{""http_status"": 599, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=server_error errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id"", ""extensions"": null}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id"", ""extensions"": []}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id"", ""extensions"": {}}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id"", ""extensions"": {""code"": null}}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id"", ""extensions"": {""code"": 1}}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id"", ""extensions"": {""code"": true}}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id"", ""extensions"": {""code"": ""BUDGET""}}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id"", ""extensions"": {""nested"": {""code"": ""budget""}}}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id"", ""extensions"": {""code"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id"", ""extensions"": {""code"": ""budget""}}]}", @"http=ok errors=rate_or_resource"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""Unauthorized"", ""extensions"": {""code"": ""budget""}}]}", @"http=ok errors=mixed"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""Unauthorized""}, {""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=ok errors=mixed"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""Unauthorized""}, {""message"": ""Unauthorized""}]}", @"http=ok errors=authentication"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id"", ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id"", ""path"": [""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""], ""extensions"": {""nested"": {""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}}}]}", @"http=ok errors=unclassified"),
            (@"{""http_status"": 200, ""errors"": []}", @"http=ok errors=invalid"),
            (@"{""http_status"": 200, ""errors"": null}", @"http=ok errors=invalid"),
            (@"{""http_status"": 200, ""errors"": {}}", @"http=ok errors=invalid"),
            (@"{""http_status"": 200, ""errors"": [1]}", @"http=ok errors=invalid"),
            (@"{""http_status"": 200, ""errors"": [{}]}", @"http=ok errors=invalid"),
            (@"{""http_status"": 200, ""errors"": [{""message"": null}]}", @"http=ok errors=invalid"),
            (@"{""http_status"": 200, ""errors"": [{""message"": 1}]}", @"http=ok errors=invalid"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""Unauthorized""}, {}]}", @"http=ok errors=invalid"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}, {""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}, {""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}, {""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}, {""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}, {""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}, {""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}, {""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}, {""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=ok errors=invalid"),
            (@"{""http_status"": 200, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}, {""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}, {""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}, {""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}, {""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}, {""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}, {""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}, {""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}", @"http=ok errors=unclassified"),
        };
        foreach (var item in cases) {
            if (Interpret(Encoding.UTF8.GetBytes(item.Projection)) != item.Expected) throw new Exception();
        }
        // Test every bounded suffix, including bracketed zone identifiers.
        foreach (var template in OfflineTemplates) {
            if (!template.Pattern.Contains(@"[^\r\n]{0,512}")) continue;
            string skeleton = template.Pattern.Replace(@"\[", "[").Replace(@"\]", "]");
            string accepted = skeleton.Replace(@"[^\r\n]{0,512}", new string('x', 512));
            string refused = skeleton.Replace(@"[^\r\n]{0,512}", new string('x', 513));
            string unicode = skeleton.Replace(@"[^\r\n]{0,512}", new string('雪', 512));
            foreach (var item in new [] { (accepted, template.Category), (unicode, template.Category), (refused, "unclassified") }) {
                string raw = JsonSerializer.Serialize(new { http_status = 200, errors = new [] { new { message = item.Item1 } } });
                if (Interpret(Encoding.UTF8.GetBytes(raw)) != "http=ok errors=" + item.Item2) throw new Exception();
            }
        }
        string[] rejected = {
            @"{""http_status"": true, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}",
            @"{""http_status"": ""200"", ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}",
            @"{""http_status"": 99, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}",
            @"{""http_status"": 600, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}",
            @"{""http_status"": 200.5, ""errors"": [{""message"": ""PRIVATE-HOSTILE https://evil.invalid/ TOKEN account-id""}]}",
            @"{""http_status"":200,""http_status"":200,""errors"":[{""message"":""PRIVATE""}]}",
            @"{""http_status"":200,""errors"":[{""message"":""PRIVATE"",""message"":""Unauthorized""}]}",
            @"{""http_status"":200,""errors"":[{""message"":""PRIVATE"",""extensions"":{""code"":""budget"",""code"":""PRIVATE""}}]}",
            @"{""http_status"":200,""errors"":[{""message"":""PRIVATE"",""path"":{""PRIVATE"":1,""PRIVATE"":2}}]}",
            @"{""http_status"":200,""errors"":[{""message"":""PRIVATE"",""extensions"":[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[0]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]}]}",
            @"{""PRIVATE"":",
        };
        foreach (string raw in rejected) {
            bool refused = false;
            try { Interpret(Encoding.UTF8.GetBytes(raw)); } catch { refused = true; }
            if (!refused) throw new Exception();
        }
        bool oversized = false;
        try { Interpret(new byte[131073]); } catch { oversized = true; }
        if (!oversized) throw new Exception();
    }
    /// <summary>Decrypt authenticated bytes in memory and emit only public error classes.</summary>
    public static string Classify(byte[] envelope, byte[] privateKey, bool offline = false) {
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
            if (offline) return Interpret(frame.AsMemory(4,length));
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
        [PrivateProviderCrypto]::SyntheticOffline()
        [PrivateProviderCrypto]::Synthetic()
        [PrivateProviderCrypto]::Boundary((Join-Path $PSScriptRoot 'private_provider_capture.py'))
        if ($IsWindows) {
            $sid = 'S-1-5-21-1-2-3-1001'
            $good = [Security.AccessControl.DirectorySecurity]::new()
            $good.SetSecurityDescriptorSddlForm("O:${sid}D:P(A;OICI;FA;;;${sid})")
            if (-not (Test-OwnerOnlyAcl $good $sid $true)) { throw 'acl' }
            foreach ($sddl in @("O:${sid}D:NO_ACCESS_CONTROL", "O:${sid}D:P", "O:${sid}D:P(A;;FA;;;WD)", "O:${sid}D:P(D;;FA;;;${sid})", "O:${sid}D:(A;;FA;;;${sid})")) {
                $bad = [Security.AccessControl.DirectorySecurity]::new()
                $bad.SetSecurityDescriptorSddlForm($sddl)
                if (Test-OwnerOnlyAcl $bad $sid $true) { throw 'acl' }
            }
        }
        Write-Output 'private_capture_crypto=PASS'
        exit 0
    }
    if ($Mode -in @('keygen','classify','classify-offline')) {
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
                if (-not (Test-OwnerOnlyAcl (Get-Acl -LiteralPath $folder) $sid.Value $true)) { throw 'acl' }
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
                if (-not (Test-OwnerOnlyAcl $acl $sid ($path -eq $folder))) { throw 'acl' }
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
        $category = [PrivateProviderCrypto]::Classify($raw.ToArray(),[IO.File]::ReadAllBytes($keyPath),($Mode -eq 'classify-offline'))
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
