# Katana Batch Dispatch Skill (katana_batch_dispatch_skill.md)

> Part of the katana-mcp skill pack. Load this document before building any
> multi-shot / multi-variable render setup: Graph State Variables (GSV),
> parameter overrides, batch-mode rendering, or farm submission. All node
> types, parameter paths, CLI flags and API calls below were extracted from
> the official Katana 9.0v1 demo projects (`graph_state_variables_basic`,
> `NAPO__NativeUSD_Full_Multi-Shot_Example`, `turntable_project`), verified
> against a live Katana 9.0v1 session, and cross-checked with
> `katanaBin.exe --help` on Katana 9.0v1.

## 1. Core Concepts: Graph State Variables (GSV)

A GSV is a **project-global string variable** that expressions and
variable-aware nodes read during a cook. Changing the GSV value re-routes
the graph (different shot assets, different light rigs, different outputs)
without touching node connections.

### Creating a GSV (verified live)

```python
from NodegraphAPI import GetRootNode

root = GetRootNode()
varsp = root.getParameter('variables')

gsv = varsp.createChildGroup('shot')
gsv.createChildNumber('enable', 1.0)
gsv.createChildString('value', '1010')
gsv.createChildString('options', '1010|1020|1040|1041|1042')   # popup menu
```

- Structure: `variables.<name>` group with children `enable` (number),
  `value` (string), `options` (string, `|`-separated).
- **GSVs are always strings.** Arithmetic needs a cast: `int(getVar("shot"))`.
- Read the current value in any expression with `getVar('shot')`:

```
project.dir+'/show/sequences/SE010/USD/shot/shot_C0010_S'+getVar('shot')+'.usda'
```

- Change the active value at runtime (re-cooks dependent branches):

```python
from Katana import Utils
root.getParameter('variables.shot.value').setValue('1020', 0)
Utils.EventModule.ProcessAllEvents()   # ★ flush AFTER the change, before re-cook
```

## 2. Variable-Aware Nodes (from official examples)

| Task | Node type | Key parameters | Real example |
| :--- | :--- | :--- | :--- |
| Route by GSV | `VariableSwitch` | `variableName`; input ports **named after GSV values** (`1010`, `1020`, `single`, `threePoint`) | NAPO multi-shot: `variableName='shot'`, ports `1010/1020/1040/1041/1042` |
| Set GSV mid-graph | `VariableSet` | `variableName`, `variableValue` | `VariableSet_lightSetup_threePoint`: `lightSetup=threePoint` |
| Delete local GSV | `VariableDelete` | `variableName` | used to drop the internal `gafferState` variable before renders |
| GSV-gated group | `VariableEnabledGroup` | `variableName`, `pattern` (matched against value; `*` wildcards OK) | `VariableEnabledGroup_animateGeo`: `variableName='animateGeo'`, `pattern='yes'`; NAPO: `JOAO_HAIR` gated on `shot` |
| UI/cook split | `VariableSwitch` on `gafferState` | ports `ui` / `cook` | official demos route Viewer-only branches through a `gafferState` variable so batch cooks skip UI helpers |

Override logic pattern from `graph_state_variables_basic.xml`:

```
                    ┌── VariableSet(lightSetup=single)     ──┐
 upstream ── Merge ◄┤                                        ├─ VariableSwitch(lightSetup)
                    └── VariableSet(lightSetup=threePoint)  ─┘   ports: single | threePoint
```

## 3. Batch Mode (headless rendering)

Verified flags from `katanaBin.exe --help` (Katana 9.0v1):

```bat
"%KATANA_ROOT%\bin\katanaBin.exe" --batch ^
    --katana-file="D:\show\seq010\lighting_v012.katana" ^
    --render-node=RENDER_SETTINGS ^
    -t 1001-1050 ^
    --var shot=1010 ^
    --threads3d=16
```

| Flag | Purpose |
| :--- | :--- |
| `--batch` | Headless render mode (requires `--katana-file` and `-t`) |
| `--katana-file=<path>` | Project to load |
| `-t <range>[,<range>]` | Frame range(s), e.g. `-t 1001,1010-1020` |
| `--render-node=<Name>[@timerange][=path]` | Node to render; optional per-node frame limit and output override. Repeatable for multiple outputs |
| `--var <name>=<value>` | **Override a project GSV** — this is THE multi-shot switch: `--var shot=1020` |
| `--threads2d / --threads3d` | Thread control for 2D nodes / renderer |
| `--render-views=a,b` | Multi-view renders |
| `--crop-rect=l,b,w,h` | Region render |
| `--tile-render=x,y,xTotal,yTotal` (+ `--tile-stitch`, `--tile-cleanup`) | Split-frame tile rendering across machines |
| `--reuse-render-process` | Export Op trees for all frames first, then render the sequence in one renderer process |
| `--prerender-publish=<file>` / `--postrender-publish=<file>` | Asset-management publish hooks |
| `--make-lookfilebake-scripts=<dir>` | Emit LookFileBake scripts for the cue |
| `--script=<file.py>` / `--shell` | Headless Python (non-render automation) |

Important constraints (see also LookDev Pitfall #9):

- `--batch` renders only; arbitrary graph scripting uses `--script` (headless
  Python) or a GUI instance driven via katana-mcp.
- The project file must already contain the Render/RenderSettings node named
  in `--render-node`.
- `--var` overrides do **not** modify the saved file; they apply per launch.

## 4. Multi-Shot Dispatch Pattern

The production loop (what a farm submitter or a local wrapper does):

```python
import os
import subprocess

KATANA = r'C:\Program Files\Katana9.0v1\bin\katanaBin.exe'
PROJECT = r'D:\show\seq010\lighting_v012.katana'

SHOTS = {
    '1010': '1001-1048',
    '1020': '1001-1072',
    '1040': '1001-1060',
}

env = dict(os.environ)
env['KTOA_ROOT'] = r'C:\ktoa\ktoa-4.5.2.0-kat9.0-windows'   # renderer env
env['KATANA_RESOURCES'] = env['KTOA_ROOT'] + ';' + env.get('KATANA_RESOURCES', '')
env['PATH'] = env['KTOA_ROOT'] + r'\bin;' + env['PATH']

for shot, frames in SHOTS.items():
    cmd = [KATANA, '--batch',
           '--katana-file=%s' % PROJECT,
           '--render-node=RENDER_SETTINGS',
           '-t', frames,
           '--var', 'shot=%s' % shot]
    log_path = r'D:\show\seq010\logs\render_%s.log' % shot
    with open(log_path, 'w') as log:
        rc = subprocess.call(cmd, stdout=log, stderr=subprocess.STDOUT, env=env)
    print(shot, 'exit', rc)
```

Design rules:

1. **One project file, N GSV values** — never duplicate the .katana per shot.
   All shot-dependence (asset path, camera path, frame range, output path)
   flows from `getVar('shot')` expressions and `VariableSwitch` branches.
2. **Output paths must contain the GSV**, e.g. on
   `RenderOutputDefine`'s `locationSettings.renderLocation`:
   `project.dir+'/renders/S'+getVar('shot')+'/beauty.####.exr'` — otherwise
   shots overwrite each other.
3. **Launch environment carries the renderer**: set `KTOA_ROOT` /
   `RMANTREE` / `KATANA_RESOURCES` / `PATH` in the batch wrapper (same
   variables as the interactive launcher .bat) or the farm machine fails
   with "renderer not available".
4. **Per-shot frame ranges** live in the dispatch table (SHOTS dict), passed
   via `-t`; the project itself keeps its default range.

## 5. In-Session Rendering (GUI / scripted session)

For iterating inside a running Katana (e.g. via katana-mcp), the verified
API surface is `Katana.RenderManager`:

```python
import Katana
from NodegraphAPI import GetNode

render_node = GetNode('RENDER_SETTINGS')
Katana.RenderManager.StartRender(render_node)   # queues a renderStarted event
# Katana.RenderManager.CancelRender(stallOnCompletion=True)
# Katana.RenderManager.TriggerManualRender()    # repeat last render
```

Combined with GSV switching, a poor-man's multi-shot loop in one session:

```python
from Katana import Utils
root_vars = GetNode('').getParameter('variables')  # root node
for shot in ('1010', '1020', '1040'):
    root_vars.getParameter('shot.value').setValue(shot, 0)
    Utils.EventModule.ProcessAllEvents()            # ★ order matters
    Katana.RenderManager.StartRender(GetNode('RENDER_SETTINGS'))
    # NOTE: StartRender is asynchronous — for sequential renders use the
    # batch CLI (§4), or wait on the renderFinished event.
```

For farm integration, `Katana.FarmAPI` provides the plugin surface:
`FarmAPI.Job`, `FarmAPI.WriteFarmFile`, `FarmAPI.BaseFarmPlugin`,
`FarmAPI.GetSortedDependencyList` — a custom farm plugin collects the
render node + GSV matrix and writes one job per (shot, frame-chunk).

## 6. Pitfalls & Gotchas

1. **GSV override flag is `--var name=value`** (two separate argv tokens or
   `--var=name=value`) — it overrides the *global* project GSV; there is no
   per-node GSV flag.
2. **GSVs are strings everywhere**: `getVar('frame')` arithmetic, numeric
   comparisons, and port names on VariableSwitch all compare strings;
   `int(getVar("shot"))` for math (NAPO example does exactly this).
3. **Flush after changing, before cooking**: `setValue()` on
   `variables.<name>.value` then `Utils.EventModule.ProcessAllEvents()` —
   reversing the order yields the stale cook (LookDev Pitfall #14).
4. **`--batch` cannot run construction scripts** — it requires
   `--katana-file` + `-t` and only renders. Graph-building automation runs
   headless via `--script` or in a GUI session.
5. **VariableSwitch ports are value names, not indices**: adding a new shot
   means adding a port literally named `1050`, and the GSV `options` string
   should list it too or the UI popup won't offer it.
6. **Clean up helper variables before rendering**: the official demos insert
   `VariableDelete` for the internal `gafferState` variable so UI-state
   variables don't leak into render cooks.
7. **Relative output paths resolve against the project file**, which on a
   farm node may differ — always build `renderLocation` from `project.dir`
   or an absolute show root passed via another GSV (e.g. `--var showRoot=...`).
8. **StartRender is asynchronous** — never loop `StartRender` back-to-back
   expecting sequential frames; use batch CLI per (shot, range) for
   deterministic sequential output.
9. **License check happens at launch**: a batch node without a Katana
   render license fails before reading the project; verify with
   `katanaBin --batch --katana-file=<minimal> -t 1` on each new farm image.
