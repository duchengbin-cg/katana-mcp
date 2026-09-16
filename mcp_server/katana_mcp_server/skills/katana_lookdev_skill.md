# Katana LookDev Construction Guide & Specification (Katana LookDev Skill)

> **Data provenance**: distilled from 42 official `.katana` projects — the Katana 9.0v1
> demo suite (`demos/katana_files`) and the NAPO Multi-Shot example projects —
> exported to XML via `NodegraphAPI.BuildNodesXmlIO` and analyzed statistically.
> Every node type, parameter path and API call in this document either appears in
> that XML data or was verified live on Katana 9.0v1 + KtoA 4.5.2.0 (Arnold 7.5.2.0)
> with RenderMan For Katana 27.2 also installed.
> Renderer identifiers observed in real files: `prman`, `arnold`, `dl` (3Delight),
> `Redshift` (capital R).

---

## 1. Core Topology & Data Flow

The official examples share a remarkably consistent main stream
(upstream → downstream):

```
[Asset]    Alembic_In / UsdIn / UsdReferenceSet ─┐
[Camera]   CameraCreate ──────────────────────────┤
[Material] NetworkMaterialCreate ──→ Merge ───────┤
           (shading nodes feed the NMC inputs)     │
                                                   ▼
                                        Merge (geo + cam + materials)
                                                   │
           MaterialAssign (binds materials via CEL) ←─┘
                                                   │
           GafferThree (light rig; takes the stream in) ←─┘
                                                   │
           <renderer>ObjectSettings / AttributeSet (per-object attrs via CEL)
                                                   │
           <renderer>OutputChannelDefine (declares AOV channels; chainable)
                                                   │
           RenderOutputDefine (declares render outputs / channel mapping)
                                                   │
           RenderSettings (renderer / cameraName / resolution)
                                                   │
           Render (execution node)
```

Observed conventions (FirstKatanaProject series, turntable_project,
material_creating, aovs_*):

- **Geometry and cameras merge first**; material networks
  (`NetworkMaterialCreate`) merge into the same stream, then `MaterialAssign`
  binds them with CEL.
- **`GafferThree` sits inline on the main stream** (it has an `in` port).
  Lights live inside it as *packages*; its output carries the `lightList`
  attribute.
- **AOVs are two layers**: declare channels first
  (`ArnoldOutputChannelDefine` / `PrmanOutputChannelDefine`, both have
  `in`/`out` and can be chained), then define file outputs
  (`RenderOutputDefine`).
- **`RenderSettings` terminates the main chain**; a `Render` node hangs off
  the end to trigger rendering.
- Variation is handled with Graph State Variables: `VariableSet` →
  `VariableSwitch` branches; camera switching with `Switch`/`VariableSwitch`
  over multiple `CameraCreate` nodes.

### LookFile workflow (robot_lookfile_*, look_files_and_look_development)

```
Material network → LookFileBake (.klf)                 # bake
Scene stream     → LookFileAssign (CEL + asset=klf)    # assign
                 → LookFileResolve                     # resolve (immediate)
                 → (or deferred resolve via RenderSettings)
Material export: Material network → LookFileMaterialsOut (.klf)
Material import: LookFileMaterialsIn → MaterialAssign
Globals:         LookFileGlobalsAssign (register klf as scene-wide defaults)
Management:      LookFileManager (curate multiple klf passes)
```

### Native USD variant (native_USD_*, NAPO examples)

`UsdIn / UsdReferenceSet → UsdGaffer (lights) / UsdMaterial → UsdLayerDefine
→ UsdLayerExport`, bridged to the classic Geolib stream with `Teleport`
nodes; AOV/render node chain is unchanged.

---

## 2. Node Type & Function Registry

Parameter paths are taken verbatim from the exported XML
(relative to the node's parameter root).

| Purpose | Node Type | Key Ports (In/Out) | Core Parameter Paths |
| :--- | :--- | :--- | :--- |
| Alembic import | `Alembic_In` | -/`out` | `abcAsset` (file), `name` (scene location), `fps`, `timing.mode` |
| USD import | `UsdIn` | -/`out` | `fileName`, `location`, `isolatePath`, `variants`, `prePopulate` |
| USD reference edit | `UsdReferenceSet` | `in`/`out` | `location`, reference/variant params |
| Built-in primitive | `PrimitiveCreate` | -/`out` | `name`, `type` (e.g. `poly sphere`), `transform.*` |
| Camera | `CameraCreate` | -/`out` | `name` (default `/root/world/cam/camera`), `projection`, `fov`, `near`, `far`, `transform.*` |
| Merge streams | `Merge` | dynamic `i0..iN`/`out` | `advanced.sumBounds`, `advanced.mergeGroupAttributes` |
| Branch switch | `Switch` | dynamic `i0..iN`/`output` | `in` (0-based index, expression-capable) |
| GSV switch | `VariableSwitch` | dynamic multi-in/`out` | `variableName`, `patterns.iN` |
| Set GSV | `VariableSet` | `in`/`out` | `variableName`, `variableValue` |
| Delete GSV | `VariableDelete` | `in`/`out` | `variableName` |
| Material network | `NetworkMaterialCreate` | dynamic inputs/`out` | `rootLocation` (default `/root/materials`), `_rendererContext` |
| Edit material network | `NetworkMaterialEdit` | `in`/`out` | references target NMC internally |
| Classic material | `Material` | `in`/`out` | `action`, `namespace`, `addShaderType`, `edit.location`, `lookfile.lookfile` |
| Arnold shading node | `ArnoldShadingNode` | dynamic (per nodeType)/`out` | `nodeType` (e.g. `standard_surface`), `parameters.*` (generated after nodeType) |
| RenderMan shading node | `PrmanShadingNode` | dynamic/`out` | `nodeType` (e.g. `PxrSurface`), `parameters.*` |
| 3Delight shading node | `DlShadingNode` | dynamic/`out` | `nodeType`, `parameters.*` |
| Material assignment | `MaterialAssign` | `in`/`out` | `CEL`, `args.materialAssign.value` (material scene path) |
| Light rig | `GafferThree` | `in`/`out` | `rootLocation`, `showIncomingScene` (lights mount as packages, see §5) |
| Single light | `LightCreate` | -/`out` | `name` (default `/root/world/lgt/light`), `transform.*`, `lightListDefaults` |
| CEL collection | `CollectionCreate` | -/`out` | `name` (referenced as `$name`), `CEL`, `location` |
| Object settings (Arnold) | `ArnoldObjectSettings` | `in`/`out` | `CEL`, `args.*` (visibility/subdiv …) |
| Object settings (prman) | `PrmanObjectStatements` | `in`/`out` | `CEL`, `args.*` |
| Generic attribute | `AttributeSet` | `in`/`out` | `paths.i0`, `attributeName`, `attributeType`, `stringValue.i0` |
| Custom Op (Lua) | `OpScript` | `in`/`out` | `CEL`, `script.lua`, `executionMode`, `applyWhere` |
| Generic Op | `GenericOp` | dynamic/`out` | `opType`, `opArgs.*`, `CEL` |
| Location creation | `LocationCreate` | -/`out` | `type`, `locations`, `attrs.*` |
| Isolate | `Isolate` | `in`/`out` | `isolateLocations`, `isolateFrom` |
| Prune | `Prune` | `in`/`out` | `cel` (lowercase!) |
| Transform | `Transform3D` | `in`/`out` | `path`, `transform.*`, `makeInteractive` |
| AOV channel (Arnold) | `ArnoldOutputChannelDefine` | `in`/`out` | `name`, `channel` (AOV name), `type` (RGBA/FLOAT), `filter`, `driver`, `lightPathExpression`, `nodes.driverParameters.filename` |
| AOV channel (prman) | `PrmanOutputChannelDefine` | `in`/`out` | `name` (e.g. `lpe:directDiffuse`), `type`, `params.paramN.*` |
| Render output | `RenderOutputDefine` | `input`/`out` | `outputName`, `args.renderSettings.outputs.<name>.*` |
| Render settings | `RenderSettings` | `input`/`out` | `CEL` (`/root`), `args.renderSettings.{renderer,cameraName,resolution}.value` |
| Render execution | `Render` | `input`/- | upstream is RenderSettings; triggers rendering |
| LookFile bake | `LookFileBake` | `orig`/`out` | `rootLocations`, `passes`, `saveTo`, `options.*` |
| LookFile assign | `LookFileAssign` | `in`/`out` | `CEL`, `args.lookfile.asset` (.klf path) |
| LookFile resolve | `LookFileResolve` | `in`/`out` | `CEL` (often empty = global) |
| LookFile materials out | `LookFileMaterialsOut` | `in`/`out` | `saveTo` |
| LookFile materials in | `LookFileMaterialsIn` | -/`out` | `lookfile`, `materialPath` |
| Graph tidying | `Dot` / `Teleport` | `in`/`out` | Teleport pairs via `portName` |

---

## 3. CEL (Collection Expression Language) Best Practices

Real patterns from the official examples:

```text
/root/world/geo/Robot                                    # exact single path (braces optional)
(/root/world/geo/char_joao /root/world/geo/char_avo)     # multiple paths, space separated
/root/world/geo//*                                       # // = descendants at any depth
/root/world/geo//*BodyShell*                             # * = name wildcard
/root/world/geo//*{@type == "polymesh"}                  # {@attr == "value"} attribute filter
/root/world/geo//*{@type == "polymesh"} + (/root/world/geo//*{@type == "subdmesh"})
                                                         # + union / - difference
(($char*//Hair_scalp*)) + (...)                          # $name references a CollectionCreate set
(/$FG /$MG /$Glass)                                      # collections commonly group lights/objects
((/root/world/geo/Env_house/*/*/*)) - ((/root/world/geo/Env_house/Lounge_grp/prop_armchair))
```

Rules of thumb:

- `MaterialAssign.CEL` usually binds exact paths `(/root/world/geo/...)`;
  object-settings nodes batch-match with `*{@type==...}`.
- `//` means "self and descendants", `*` matches any single name component;
  collection names are referenced with a `$` prefix
  (`CollectionCreate.name` itself has no `$`).
- `RenderSettings.CEL` is fixed to `/root` (settings land on root attributes).
- CEL evaluates against the **upstream** scene graph: a collection must be
  created by `CollectionCreate` upstream of where it is referenced.

---

## 4. Standard Python Construction Blueprint

Every API call below was verified live on Katana 9.0v1
(including the corrections learned from real failures):

```python
from NodegraphAPI import GetRootNode, CreateNode, SetNodePosition

root = GetRootNode()

# --- Asset + camera + merge ---------------------------------------------
abc = CreateNode('Alembic_In', root); abc.setName('Asset_In')
abc.getParameter('abcAsset').setValue('/path/to/asset.abc', 0)

cam = CreateNode('CameraCreate', root); cam.setName('Lookdev_CAM')
cam.getParameter('name').setValue('/root/world/cam/lookdev_cam', 0)

merge = CreateNode('Merge', root); merge.setName('MERGE_Scene')
merge.addInputPort('i0').connect(abc.getOutputPort('out'))   # dynamic input ports
merge.addInputPort('i1').connect(cam.getOutputPort('out'))

# --- Material: NetworkMaterialCreate + shading node ----------------------
nmc = CreateNode('NetworkMaterialCreate', root); nmc.setName('Asset_NMC')
shd = CreateNode('ArnoldShadingNode', root)
shd.getParameter('nodeType').setValue('standard_surface', 0)
shd.checkDynamicParameters()            # ★ REQUIRED, see Pitfalls #1
nmc.addInputPort('arnoldSurface').connect(shd.getOutputPort('out'))

ma = CreateNode('MaterialAssign', root); ma.setName('Asset_MA')
ma.getParameter('CEL').setValue('(/root/world/geo/asset)', 0)
ma.getParameter('args.materialAssign.value').setValue(
    '/root/materials/Asset_NMC', 0)
ma.getInputPort('in').connect(merge.getOutputPort('out'))

# --- Lights: GafferThree + KtoA HDRI skydome package ---------------------
gaf = CreateNode('GafferThree', root); gaf.setName('LIGHT_RIG')
gaf.getInputPort('in').connect(ma.getOutputPort('out'))

from Katana import Plugins
pkg_cls = Plugins.GafferThreeAPI.PackageClasses.ArnoldHDRISkydomeLightPackage
pkg = pkg_cls.create(gaf, '/root/world/lgt/gaffer/hdri_key')
gaf.getRootPackage().adoptPackage(pkg)  # ★ REQUIRED, see Pitfalls #2

# --- AOV channels + render output + render settings ----------------------
prev = gaf
for nm, ch in (('beauty', 'RGBA'), ('N', 'N'), ('P', 'P'),
               ('diffuse_direct', 'diffuse_direct'),
               ('crypto_asset', 'crypto_asset')):
    n = CreateNode('ArnoldOutputChannelDefine', root); n.setName('AOV_' + nm)
    n.getParameter('name').setValue(nm, 0)
    n.getParameter('channel').setValue(ch, 0)
    n.getInputPort('in').connect(prev.getOutputPort('out'))
    prev = n

rod = CreateNode('RenderOutputDefine', root); rod.setName('OUTPUTS')
rod.getInputPort('input').connect(prev.getOutputPort('out'))
rod.getParameter('outputName').setValue('primary', 0)

# Standard GenericAssign leaf structure: enable / value / default / type
def ga_leaf(parent, name, value, attr_type='StringAttr'):
    g = parent.createChildGroup(name)
    g.createChildNumber('enable', 1.0)
    g.createChildString('value', str(value))
    g.createChildString('default', str(value))
    g.createChildString('type', attr_type)
    return g

outs = rod.getParameter('args.renderSettings.outputs')
prim = outs.createChildGroup('primary')
ga_leaf(prim, 'type', 'color')
ga_leaf(prim, 'fileExtension', 'exr')
rs = prim.createChildGroup('rendererSettings')
ga_leaf(rs, 'channel', 'beauty,N,P,diffuse_direct,crypto_asset')  # KtoA: comma list

rsn = CreateNode('RenderSettings', root); rsn.setName('RENDER_SETTINGS')
rsn.getInputPort('input').connect(rod.getOutputPort('out'))

def ga_set(node, path, value):          # set an existing GenericAssign parameter
    p = node.getParameter('args.renderSettings.' + path)
    p.getChild('enable').setValue(1.0, 0)
    p.getChild('value').setValue(value, 0)

ga_set(rsn, 'renderer', 'arnold')       # 'prman' / 'dl' / 'Redshift' likewise
ga_set(rsn, 'cameraName', '/root/world/cam/lookdev_cam')

rnode = CreateNode('Render', root); rnode.setName('Render')
rnode.getInputPort('input').connect(rsn.getOutputPort('out'))
```

Group-based templating pattern (parameterized, reusable template):

```python
G = CreateNode('Group', root); G.setName('LOOKDEV')
G.addOutputPort('out')
user = G.getParameters().createChildGroup('user')
p = user.createChildString('assetPath', '')
p.setHintString(str({'widget': 'fileInput'}))      # ★ single dict-string argument

# Inner nodes reference group parameters via expressions:
inner.getParameter('abcAsset').setExpression('=^/user.assetPath')  # ^ = parent group
# or by node name (also verified):
inner.getParameter('abcAsset').setExpression("getParam('LOOKDEV.user.assetPath')")

# Inner last node -> group output port: MUST use the return port
last_node.getOutputPort('out').connect(G.getReturnPort('out'))
```

---

## 5. Pitfalls & Gotchas

All of the following were hit and diagnosed on a real Katana 9.0v1 session,
ordered by likelihood of encountering them:

1. **Shading-node parameters don't appear**: after setting `nodeType` on
   `ArnoldShadingNode` / `PrmanShadingNode`, the `parameters` group and input
   ports are **not generated automatically**. Call
   `node.checkDynamicParameters()` — this is exactly what KtoA's own
   `ArnoldHDRISkydomeLightPackage.createShadingNetwork` does. The UI triggers
   it via the editor; headless scripts must call it explicitly.
2. **GafferThree packages never reach the scene**:
   `PackageClass.create(gaf, path)` only builds the package node. You must
   also `gaf.getRootPackage().adoptPackage(pkg)` — otherwise
   `getChildPackages()` is empty, cooking produces no lights under
   `/root/world/lgt/gaffer`, and the `lightList` attribute is missing.
   After adoption, lights cook at `/root/world/lgt/gaffer/<name>` with a
   `skydome_light` + `image` material (the surface shader auto-wires into
   the light's `color`).
3. **Katana expressions are a restricted DSL, not full Python**:
   `getParam('NODE.param')` reads values, `==` comparisons work, ternary
   `1 if ... else 0` works — but **string methods silently fail**
   (`.lower()` / `.endswith()` / `len()` all collapse to 0). Do not
   implement "auto-detect file extension" logic in expressions; use a popup
   parameter with manual selection, or Lua in an OpScript.
4. **Group output port direction**: to connect an internal node to a Group's
   output, the target must be `G.getReturnPort('out')`. Connecting to
   `G.getOutputPort('out')` raises "same type" (both are producer ports).
5. **GenericAssign leaf structure**: `RenderSettings` / `RenderOutputDefine` /
   `MaterialAssign` / `Material` are GenericAssign-family nodes. Parameter
   leaves must use the four-part `enable/value/default/type` structure
   (optionally `__hints`). A bare `createChildString('filename', v)` leaf is
   **silently ignored** — the attribute never reaches the scene.
6. **KtoA's two-layer AOV model**: `ArnoldOutputChannelDefine` writes
   `arnoldGlobalStatements.outputChannels.<name>` (channel = AOV name,
   filter, driver); `RenderOutputDefine` writes
   `renderSettings.outputs.<name>`, where `rendererSettings.channel` is a
   **comma-separated list of channel names** (that is how a multi-channel
   single EXR is produced) and `locationSettings.renderLocation` is the file
   path. Use `closest_filter` for data AOVs (N/P/Z/crypto) and
   `gaussian_filter` for color AOVs.
7. **Dynamic input ports**: `Merge` / `Switch` / `VariableSwitch` /
   `NetworkMaterialCreate` start with no input ports — call
   `addInputPort('i0')` before `connect`. `Switch`'s selector parameter is
   `in` (0-based) and its output port is named `output` (not `out`).
8. **`setHintString` signature**: takes **one** string (the stringified hints
   dict), not a key/value pair.
9. **Batch mode is for rendering only**: `katanaBin --batch` requires
   `--katana-file` plus a `-t` frame range and cannot run arbitrary scripts.
   For scripted construction/export, drive a GUI instance (e.g. via
   katana-mcp or `--script`). Beware modal dialogs when loading projects
   that reference uninstalled renderers (Redshift/3Delight).
10. **Loading a project discards unsaved changes**: wrap
    `Katana.KatanaFile.Load()` with
    `PushFileDirtyState()/PopFileDirtyState()` to suppress the
    unsaved-changes prompt during scripted batch exports.
11. **Renderer identifier casing**: verified `renderer` values are `prman`,
    `arnold`, `dl`, `Redshift` (note the capital R, and 3Delight is `dl`).
    Project files carry their own renderer settings; the
    `DEFAULT_RENDERER` environment variable only affects new scenes.
12. **KtoA has no standalone light node**: KtoA 4.x registers no
    `ArnoldLight` node type. Lights are created via GafferThree packages
    (`ArnoldHDRISkydomeLightPackage` etc. under `KTOA_ROOT/SuperTools/`) or
    manually with `LightCreate` + a light material. Registration in the
    render is done by the package's internal `LightListEdit`, which writes
    the `lightList` attribute at `/root/world`.

---

### Appendix: dual-renderer launcher environment (KtoA + RenderMan)

Key environment for a launcher `.bat` that opens both Arnold and RenderMan
projects (verified with KtoA 4.5.2.0 + RfK 27.2 on Katana 9.0v1):

```bat
set "RMANTREE=C:\Program Files\Pixar\RenderManProServer-27.2"
set "RMSTREE=C:\Program Files\Pixar\RenderManForKatana-27.2"
set "path=%RMANTREE%\bin;%KTOA_ROOT%\bin;...;%path%"
set "KATANA_RESOURCES=%RMSTREE%\plugins\katana9.0;%KTOA_ROOT%;...;%KATANA_RESOURCES%"
```

- RfK builds per Katana version into `plugins\katana9.0` — it must be added
  to `KATANA_RESOURCES`.
- `RMANTREE\bin` must be on `PATH` (prman core DLLs).
- The two renderers coexist without conflict: node types register per
  plugin, so RenderMan projects use RfK nodes and Arnold projects use KtoA
  nodes in the same session.
