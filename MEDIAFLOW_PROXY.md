# MediaFlow Proxy

Open **Admin → Settings → Stream delivery** and configure:

1. **HTTP / MediaFlow proxy URL**: the MediaFlow base URL, for example `https://proxy.example.com`.
2. Enable **Use MediaFlow proxy format**.
3. Enter the MediaFlow `API_PASSWORD` when the server requires it.
4. Keep **Show both stream types** enabled for the first playback test.

TG Stremio generates links in this form automatically:

```text
https://proxy.example.com/proxy/stream?d=<encoded-direct-stream-url>&api_password=<encoded-password>
```

When MediaFlow mode is disabled, the existing plain prefix behavior is preserved.
