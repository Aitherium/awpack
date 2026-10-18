# free-cloud — Free cloud (your own free-tier keys)

Runs [FreeLLMAPI](https://github.com/tashfeenahmed/freellmapi) (MIT, by Tashfeen
Ahmed) on your machine and makes it awdk's **non-local route**: a local model
answers first, your own free-tier provider keys next, a paid API key last.

```bash
awpack install free-cloud      # then run the lines it prints:
pip install "awdk>=3.8.74"
adk free-cloud up              # pinned image, 127.0.0.1:3001, volume freellmapi-data
adk keys set freellmapi        # the unified key from its Keys page
adk free-cloud enable
```

**Bring your own keys.** Each user runs their own FreeLLMAPI with their own
provider accounts; those providers' terms apply to traffic it proxies, and
upstream describes it as for personal experimentation, not production. Read the
[terms-of-service review](https://github.com/tashfeenahmed/freellmapi/blob/main/docs/en/architecture/00-high-level-index.md#terms-of-service-review)
first.

- Provider keys live only in FreeLLMAPI's encrypted store.
- The unified key stays on this machine (`adk keys set freellmapi`, never synced).
- `enabled`, URL and preferred models sync across your machines through
  `awsettings --domain mods` (`~/.aither/mods.json` → `freellmapi`).

Uninstall: `awpack remove free-cloud` and `adk free-cloud down`. Your keys volume
is kept; delete it yourself only if you mean to lose those keys.

Docs: awdk `docs/providers/freellmapi.md`.
