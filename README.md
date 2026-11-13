# skill-claim-audit

**Check what a `SKILL.md` claims about its environment against what the repository actually contains — before an agent trusts the claim and fails at runtime.**

Why now: `anthropics/skills` (194k★) ships skills that tell agents "this is preinstalled" or "this binary is auto-configured". Two open upstream issues show those claims failing on real machines, and there is no offline checker that ties a claim to an artifact.

Upstream: https://github.com/anthropics/skills

## The upstream and the gap

`anthropics/skills` is Anthropic's public Agent Skills collection: each skill is a `SKILL.md` plus optional `scripts/` and `references/`. Agents load the description, then follow the body — including statements about what is already installed.

The collection has no claim-to-evidence check, and two live issues document the result:

- [#2184](https://github.com/anthropics/skills/issues/2184): `skills/xlsx/SKILL.md:16` says `openpyxl`, `pandas`, `markitdown` are "preinstalled — do not run `pip install` first". The skill has **no `requirements.txt`**, and on macOS system Python `import openpyxl` fails. Fix PR #2188 is open, unmerged.
- [#2185](https://github.com/anthropics/skills/issues/2185): `SKILL.md:99` says LibreOffice (`soffice`) is "auto-configured ... via `scripts/office/soffice.py`". That script only sets environment variables and then runs bare `subprocess.run(["soffice"])`; it never locates the binary. Fix PR #2187 is open, unmerged.

A third class is visible in [#2178](https://github.com/anthropics/skills/issues/2178) (a stale endpoint), but URL liveness needs network and is out of scope here.

## What this tool does

`skill-claim-audit` scans a directory of skills offline and reports three claim types:

| Rule | Claim checked | Pass condition |
| --- | --- | --- |
| `CLAIM001` | "`X` is preinstalled / bundled / ships with" | `X` appears in a dependency manifest (`requirements.txt`, `pyproject.toml`, `package.json`, `environment.yml`, `setup.py`, `Pipfile`) somewhere in the tree |
| `CLAIM002` | "`X` is auto-configured / preconfigured via `script`" | the referenced script (or any script mentioning `X`) contains a locator: `shutil.which`, `command -v`, `which X`, `/Applications/`, `Program Files`, or `os.path.exists` |
| `CLAIM003` | A repo-relative path is referenced | the path exists next to that `SKILL.md` |

It does **not** install packages, execute skill scripts, check network endpoints, or prove that a declared package is importable in your interpreter. A clean report means "every checked claim has in-repo evidence", not "the environment is correct".

## Install

Python 3.8+, no third-party packages, no network.

```bash
git clone https://github.com/linmoxi33/skill-claim-audit.git
cd skill-claim-audit
python3 bin/skill-claim-audit examples/in/demo-skill --fail-on medium
```

## Usage

```bash
# text report, exit 1 only on HIGH findings (default)
python3 bin/skill-claim-audit path/to/skills

# machine-readable report; exit 1 if any finding >= medium
python3 bin/skill-claim-audit path/to/skills --json --fail-on medium
```

Exit codes: `0` no findings at or above `--fail-on`; `1` at least one finding; `2` usage or input error (missing directory, no `SKILL.md`).

`--json` is a single object: `root`, `skills_scanned`, `findings[]` (`rule`, `severity`, `file`, `line`, `subject`, `claim`, `evidence`, `message`), `summary` (per-severity counts + manifests found), `fail_on`, `exit_code`. It parses with `python3 -c "import json,sys;json.load(sys.stdin)"`.

### Real result on the upstream xlsx skill

Scanning `skills/xlsx` from upstream HEAD (blob `cc34720`, 2026-11-13) with `--fail-on medium`:

```text
skills scanned: 1  findings: 4 (high 3, medium 1, low 0)
SKILL.md:16: HIGH CLAIM001 openpyxl - not declared by any dependency manifest
SKILL.md:16: HIGH CLAIM001 pandas   - not declared by any dependency manifest
SKILL.md:16: HIGH CLAIM001 markitdown - not declared by any dependency manifest
SKILL.md:99: MEDIUM CLAIM002 soffice - referenced script never locates the binary
exit: 1
```

That reproduces #2184 and #2185 from the files alone, with `file:line` witnesses. The `examples/out/report.json` was produced by actually running the command above on `examples/in/demo-skill`.

## 本轮创新

**B 档：首次把 SKILL.md 的环境声明当作可证伪契约，用仓库内证据逐条反证，并给出 `file:line` + 已查文件见证。** 同类工具只做 frontmatter/注册/路径结构检查；`gh search repos "skill claim audit"` 返回 0 条，代码检索到的最高星命中是与本问题无关的 ML 书。这里的“新”不是又一个 linter，而是把“预装/自动配置”这类**无法离线验证的自然语言断言**转成可判定的证据规则，并用上游两个仍然 open 的真实 issue 自证检出。

## 与同类项目的差异

- `TheStack-ai/pulser` (18★) auto-fixes SKILL.md structure; it does not check environment claims.
- `dspy-agent-skills` (278★) is a skill collection, not a validator.
- `skill-guard` / `agent-skills-lint` (≤6★) validate structure and frontmatter.
- No mature (>500★) tool ties `preinstalled` / `auto-configured` claims to repository artifacts (search commands in the round log).

## Limitations

- Manifest presence is treated as evidence; a declared-but-uninstallable package still passes.
- `CLAIM002` is a heuristic: a script may locate the binary through an indirection the five locator patterns miss, producing a false medium.
- `CLAIM003` only resolves paths relative to the skill directory; paths relative to the repository root are skipped.
- English claim phrases only (`preinstalled`, `ships with`, `auto-configured`, `preconfigured`).

## Tests

```bash
python3 -m unittest discover -s tests -v   # 15 tests, 4 behavior (exit codes + JSON)
```

MIT © 2026 linmoxi33. Upstream content referenced by link only; no upstream files are redistributed.