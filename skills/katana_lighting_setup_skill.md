# Katana Lighting Setup Skill (katana_lighting_setup_skill.md)

> Part of the katana-mcp skill pack. Load this document before building any
> lighting node graph (GafferThree rigs, light packages, AOV/RenderPass
> strategy, RenderOutput configuration). All node types, parameter paths and
> API calls below were extracted from the official Katana 9.0v1 demo projects
> (`native_USD_lighting_example`, `LightingExample_RENDERMAN`, `aovs`,
> `aovs_arnold`, `aovs_prman`) and verified against a live Katana 9.0v1
> session with both KtoA 4.5.2 and RenderMan 27.2 loaded.

## 1. Core Topology & Data Flow

```
[upstream scene: assembly / lookdev]
            │
            ▼
     GafferThree            ← all lights live here as *packages*
            │
            ▼
 <Renderer>OutputChannelDefine  × N   (one per AOV channel, daisy-chained)
            │
            ▼
     RenderOutputDefine     (output "primary": file type, location, channels)
            │
            ▼
      RenderSettings        (renderer id, camera, resolution, sampling)
            │
            ▼
    Render / RenderReferenceSetup → render
```

Optional branches: `LightLinkSetup` (light↔object linking), `LightListEdit`
(manual lightList registration), `GroupStack` (per-pass override stacks),
`ConstraintListEdit` (aim/parent constraints).

## 2. GafferThree Package API (verified live)

Lights in GafferThree are **packages** — self-contained node groups created
through the GafferThree API, never as bare nodes:

```python
from Katana import Plugins
g3 = Plugins.GafferThreeAPI

pkg = g3.PackageClasses.<PackageClass>.create(gaf, '/root/world/lgt/gaffer/<name>')
gaf.getRootPackage().adoptPackage(pkg)          # ★ REQUIRED — without this
                                                #   the light never cooks
mat = pkg.getMaterialNode()                      # inner Material node
```

### Package classes verified present (KtoA 4.5.2 + RfK 27.2)

| Renderer | Package classes (create → also has `<Name>EditPackage` variants) |
| :--- | :--- |
| **Arnold** | `ArnoldPointLightPackage`, `ArnoldSpotLightPackage`, `ArnoldDistantLightPackage`, `ArnoldQuadLightPackage`, `ArnoldDiskLightPackage`, `ArnoldCylinderLightPackage`, `ArnoldMeshLightPackage`, `ArnoldPhotometricLightPackage`, `ArnoldSkydomeLightPackage`, `ArnoldHDRISkydomeLightPackage`, `ArnoldHDRIQuadLightPackage`, `ArnoldHDRIMeshLightPackage`, `ArnoldPhysicalSkydomeLightPackage`, `ArnoldGoboSpotLightPackage`, `ArnoldBarnDoorsSpotLightPackage` |
| **RenderMan** | `PxrRectLightPackage`, `PxrDiskLightPackage`, `PxrSphereLightPackage`, `PxrCylinderLightPackage`, `PxrDistantLightPackage`, `PxrDomeLightPackage`, `PxrEnvDayLightPackage`, `PxrMeshLightPackage`, `PxrPortalLightPackage`, `PxrAovLightPackage` |
| **RM light filters** | `PxrBarnLightFilterPackage`, `PxrBlockerLightFilterPackage`, `PxrCookieLightFilterPackage`, `PxrGoboLightFilterPackage`, `PxrIntMultLightFilterPackage`, `PxrRampLightFilterPackage`, `PxrRodLightFilterPackage` (also generic `LightFilterPackage`, `LightFilterReferencePackage`) |
| **Utility** | `RigPackage`, `TemplateMaterialPackage`, `LightPackage`, `LightEditPackage` |

Every `XxxPackage` has a matching `XxxEditPackage` for editing existing
lights. If a package class is missing from `dir(g3.PackageClasses)`, add its
SuperTool directory to `sys.path` and import the module (pattern documented
in `katana_lookdev_skill.md`, Pitfall #12).

### Shader parameter leaves (GenericAssign rule)

Light-package Material nodes expose renderer-specific groups under
`shaders` (verified live):

| Renderer | Shader selector leaf | Parameter group leaf |
| :--- | :--- | :--- |
| Arnold | `shaders.arnoldLightShader` = `skydome_light` … | `shaders.arnoldLightParams.<param>` |
| RenderMan | `shaders.prmanLightShader` = `PxrRectLight` … | `shaders.prmanLightParams.<param>` |

Each parameter is a GA leaf: group with `enable` (number, 1), `value`
(typed), `type` (`'StringAttr'`/`'FloatAttr'`/`'IntAttr'`). Leaves created
under the generic `shaders.parameters` group are **silently dropped** at
cook time — see `katana_lookdev_skill.md` Pitfall #13.

## 3. AOV / RenderPass Strategy (from official aovs examples)

Two-layer model (KtoA and RfK both follow it):

1. **`<Renderer>OutputChannelDefine`** — declares a channel into
   `arnoldGlobalStatements.outputChannels.<name>` /
   `prmanGlobalStatements.outputChannels.<name>`.
2. **`RenderOutputDefine`** — maps channels to actual files in
   `renderSettings.outputs.<outputName>`.

### ArnoldOutputChannelDefine (verified from aovs_arnold.xml)

| Parameter | Example value | Notes |
| :--- | :--- | :--- |
| `name` | `diffuse` | AOV output name |
| `channel` | `diffuse` | Arnold AOV name (`RGBA`, `N`, `P`, `Z`, `crypto_object` …) |
| `type` | `RGBA` / `FLOAT` | `FLOAT` for Z/depth |
| `driver` | `driver_exr` | |
| `filter` | `gaussian_filter` | use `closest_filter` for data AOVs (N/P/Z/crypto) |
| `denoise` | `0` | |
| `lightPathExpression` | `C<RD>.*` | optional LPE split (diffuse example: `C<RD>.*`, specular: `C<RS[^'coat']>.*`, indirect: `C[DSV][DSVOB].*`) |
| `lightGroups` | `all` | |

Official crypto AOVs: `crypto_asset`, `crypto_object`, `crypto_material`.

### PrmanOutputChannelDefine (verified from aovs_prman.xml)

| Parameter | Example value | Notes |
| :--- | :--- | :--- |
| `name` | `lpe:diffuse` | channel name; `lpe:` prefix for LPE-based channels |
| `renderer` | `prman` | |
| `type` | `varying color` | |
| `source` | `color lpe:C[<L.>O]` | LPE source expression (string) |

### RenderOutputDefine (verified from aovs.xml)

GA-leaf structure under `args.renderSettings.outputs.<outputName>`:

```
type                 = color | raw        (GA leaf)
fileExtension        = exr
channel              = beauty             (or comma-separated channel list
                                           for multi-channel single EXR)
colorSpace           = auto
computeSettings.*    = fileType-specific (compression, bit depth…)
locationSettings.renderLocation = path   (supports expressions, e.g. GSVs)
rendererSettings.channel / cameraName / ...
```

## 4. USD-native lighting (from native_USD_lighting_example)

`UsdLight` creates/edits USD light prims directly:

| Parameter | create example | edit example |
| :--- | :--- | :--- |
| `action` | `create` | `edit` |
| `primPath` | `/lights/ceiling_light` | same prim |
| `type.enable` + `type.value` | `1` + `DiskLight` / `RectLight` | `0` (inherit) |
| `lastType` | `DiskLight` | `DiskLight` |

## 5. Standard Python Construction Blueprint

```python
from NodegraphAPI import GetRootNode, CreateNode
from Katana import Plugins

root = GetRootNode()
g3 = Plugins.GafferThreeAPI

gaf = CreateNode('GafferThree', root); gaf.setName('LIGHT_RIG')
# gaf.getInputPort('in').connect(upstream.getOutputPort('out'))

# ---- 5.1 lights ----------------------------------------------------------
def add_light(cls_name, loc, params=None):
    cls = getattr(g3.PackageClasses, cls_name)
    pkg = cls.create(gaf, loc)
    gaf.getRootPackage().adoptPackage(pkg)            # ★ never forget
    mat = pkg.getMaterialNode()
    grp = ('arnoldLightParams' if cls_name.startswith('Arnold')
           else 'prmanLightParams')
    sp = mat.getParameter('shaders.' + grp)
    for name, (value, attr_type) in (params or {}).items():
        leaf = sp.createChildGroup(name)
        leaf.createChildNumber('enable', 1.0)
        if attr_type == 'FloatAttr':
            leaf.createChildNumber('value', float(value))
        else:
            leaf.createChildString('value', str(value))
        leaf.createChildString('type', attr_type)
    return pkg

key = add_light('ArnoldHDRIQuadLightPackage', '/root/world/lgt/gaffer/key',
                {'intensity': (2.0, 'FloatAttr'),
                 'exposure': (0.0, 'FloatAttr')})
dome = add_light('PxrDomeLightPackage', '/root/world/lgt/gaffer/dome',
                 {'intensity': (1.0, 'FloatAttr'),
                  'lightColorMap': ('/path/to/env.tx', 'StringAttr')})

# ---- 5.2 AOV chain --------------------------------------------------------
AOV_NODE = {'arnold': 'ArnoldOutputChannelDefine',
            'prman': 'PrmanOutputChannelDefine'}

def add_arnold_aov(prev, name, channel, aov_type='RGBA',
                   filt='gaussian_filter'):
    n = CreateNode('ArnoldOutputChannelDefine', root)
    n.setName('AOV_' + name)
    n.getParameter('name').setValue(name, 0)
    n.getParameter('channel').setValue(channel, 0)
    n.getParameter('type').setValue(aov_type, 0)
    n.getParameter('filter').setValue(filt, 0)
    n.getInputPort('in').connect(prev.getOutputPort('out'))
    return n

prev = gaf
for nm, ch, t, f in (('beauty', 'RGBA', 'RGBA', 'gaussian_filter'),
                     ('N', 'N', 'RGBA', 'closest_filter'),
                     ('P', 'P', 'RGBA', 'closest_filter'),
                     ('Z', 'Z', 'FLOAT', 'closest_filter'),
                     ('crypto_object', 'crypto_object', 'RGBA', 'closest_filter')):
    prev = add_arnold_aov(prev, nm, ch, t, f)

# ---- 5.3 output + settings -------------------------------------------------
rod = CreateNode('RenderOutputDefine', root); rod.setName('OUTPUTS')
rod.getInputPort('input').connect(prev.getOutputPort('out'))
rod.getParameter('outputName').setValue('primary', 0)
# GA leaves — see katana_lookdev_skill.md §4 for the ga_leaf() helper:
#   args.renderSettings.outputs.primary.{type,fileExtension,channel,colorSpace}
#   ...locationSettings.renderLocation, ...rendererSettings.channel (csv list)

rsn = CreateNode('RenderSettings', root); rsn.setName('RENDER_SETTINGS')
rsn.getInputPort('input').connect(rod.getOutputPort('out'))
def ga_set(node, path, value):
    p = node.getParameter('args.renderSettings.' + path)
    p.getChild('enable').setValue(1.0, 0)
    p.getChild('value').setValue(value, 0)
ga_set(rsn, 'renderer', 'arnold')        # or 'prman'
ga_set(rsn, 'cameraName', '/root/world/cam/cam_main')
```

## 6. Pitfalls & Gotchas

1. **Unadopted packages are invisible**: `create()` without
   `gaf.getRootPackage().adoptPackage(pkg)` builds the node but the light
   never appears in `lightList` or the render (see also LookDev Pitfall #2).
2. **Wrong shader-param group is silently dropped**: Arnold →
   `shaders.arnoldLightParams`, RenderMan → `shaders.prmanLightParams`.
   The generic `shaders.parameters` group cooks to nothing (verified live).
3. **GA leaf structure is mandatory**: every light/AOV parameter leaf needs
   `enable` + `value` + `type` (number/string children); a bare
   `createChildString(name, v)` is ignored (LookDev Pitfall #5).
4. **Filter choice matters**: `closest_filter` for data AOVs
   (N/P/Z/crypto_*), `gaussian_filter` for color AOVs — mixing them produces
   filtered (blurred) IDs or aliased color.
5. **Multi-channel EXR**: set `rendererSettings.channel` on the output to a
   **comma-separated list** of channel names; one file, many AOVs
   (LookDev Pitfall #6).
6. **Renderer id casing**: `arnold`, `prman`, `dl`, `Redshift` (capital R) —
   wrong casing disables the whole output silently (LookDev Pitfall #11).
7. **Cook-cache order**: after changing a parameter, call
   `Utils.EventModule.ProcessAllEvents()` **then** re-cook; flushing before
   the change returns the stale cached scene (LookDev Pitfall #14).
8. **Light filters parent under the light location** in GafferThree
   (`/root/world/lgt/gaffer/<light>/<filter>`), not under the gaffer root.
9. **UsdLight `type.enable` must be 1** when setting a light type; `enable=0`
   means "inherit", which on a fresh prim creates a typeless (invisible)
   light.
