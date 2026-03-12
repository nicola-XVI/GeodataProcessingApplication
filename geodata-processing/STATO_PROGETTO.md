# Stato del Progetto: Migrazione da Kratos a Python Standalone

## Obiettivo
Eliminare completamente la dipendenza da KratosMultiphysics e creare un'applicazione Python standalone per la generazione di modelli 3D CFD urbani (terreno + edifici) da dati geografici.

---

## Struttura del Progetto

```
geodata-processing/
├── pyproject.toml
├── requirements.txt
├── .venv/                          ← Ambiente virtuale (creato)
├── src/
│   └── geodata/
│       ├── __init__.py
│       ├── core/
│       │   ├── containers.py       ✅ COMPLETATO
│       │   ├── mesh_part.py        ✅ COMPLETATO
│       │   ├── spatial.py          ✅ COMPLETATO
│       │   └── fields.py           ✅ COMPLETATO
│       ├── io/
│       │   ├── readers.py          ✅ COMPLETATO
│       │   ├── writers.py          ✅ COMPLETATO
│       │   └── cad_export.py       ✅ COMPLETATO
│       ├── meshing/
│       │   ├── domain.py           ✅ COMPLETATO
│       │   ├── triangulation.py    ✅ COMPLETATO
│       │   ├── tetrahedralization.py ✅ COMPLETATO
│       │   ├── refinement.py       ✅ COMPLETATO
│       │   └── boolean_ops.py      ✅ COMPLETATO
│       ├── processing/
│       │   ├── preprocessor.py     ✅ COMPLETATO
│       │   ├── importer.py         ✅ COMPLETATO
│       │   ├── terrain.py          ✅ COMPLETATO
│       │   ├── cleaning.py         ✅ COMPLETATO
│       │   └── buildings.py        ✅ COMPLETATO
│       ├── geodata/
│       │   ├── dem.py              ✅ COMPLETATO
│       │   ├── osm.py              ✅ COMPLETATO
│       │   └── coordinates.py      ✅ COMPLETATO
│       ├── cfd/
│       │   ├── model.py            ✅ COMPLETATO
│       │   ├── boundary.py         ✅ COMPLETATO
│       │   └── parameters.py       ✅ COMPLETATO
│       ├── config/
│       │   ├── settings.py         ✅ COMPLETATO
│       │   └── defaults.py         ✅ COMPLETATO
│       └── pipeline/
│           ├── runner.py           ✅ COMPLETATO
│           └── steps.py            ✅ COMPLETATO
└── tests/
    ├── test_core.py                ✅ COMPLETATO (17 test)
    ├── test_spatial_fields.py      ✅ COMPLETATO (12 test)
    ├── test_io.py                  ✅ COMPLETATO (4 test)
    ├── test_preprocessing.py       ✅ COMPLETATO (10 test)
    ├── test_config.py              ✅ COMPLETATO (5 test)
    ├── test_meshing.py             ✅ COMPLETATO (11 test)
    ├── test_buildings.py           ✅ COMPLETATO (17 test)
    ├── test_geodata.py             ✅ COMPLETATO (32 test)
    ├── test_cfd.py                 ✅ COMPLETATO (21 test)
    └── test_pipeline.py            ✅ COMPLETATO (16 test)
```

---

## Stato per Fase

### Fase 1: Core + I/O ✅ COMPLETATA
**51 test passati (tutti verdi)**

| Modulo | File | Descrizione | Stato |
|--------|------|-------------|-------|
| Core | `containers.py` | NodeContainer, ElementContainer (numpy-backed) | ✅ |
| Core | `mesh_part.py` | MeshPart (sostituisce Kratos ModelPart) | ✅ |
| Core | `spatial.py` | SpatialTree (KD-tree), PointLocator (Delaunay), compute_extrusion_height | ✅ |
| Core | `fields.py` | Distance field, gradient tet4/tri3, normali, vertex normals | ✅ |
| I/O | `readers.py` | Lettura STL, OBJ (con gruppi edifici), XYZ, mesh generica (meshio) | ✅ |
| I/O | `writers.py` | Scrittura STL, OBJ (con sub-part), GLTF/GLB, VTK, XYZ, auto-detect | ✅ |
| Config | `settings.py` | Modelli Pydantic: Domain, Terrain, Building, Mesh, Output, CFD, Project | ✅ |
| Processing | `preprocessor.py` | Cut, Shift, filter altezza, swap YZ, merge duplicati, bounding box | ✅ |
| Processing | `importer.py` | Import terreno/edifici, add geometry, split overlap, degenerate check | ✅ |

### Fase 2: Meshing ✅ COMPLETATA
**11 test passati (tutti verdi)**

| Modulo | File | Descrizione | Stato |
|--------|------|-------------|-------|
| Meshing | `domain.py` | Dominio cilindrico con terreno, settori vento | ✅ |
| Meshing | `triangulation.py` | Triangolazione 2D (wrapper triangle lib) | ✅ |
| Meshing | `tetrahedralization.py` | Mesh volumetrica (gmsh), da STL, con size field | ✅ |
| Meshing | `refinement.py` | Raffinamento adattivo (gmsh fields), distance-based | ✅ |
| Meshing | `boolean_ops.py` | Sottrazione edifici (trimesh boolean + re-tet) | ✅ |
| Processing | `terrain.py` | Extrusion height, distance from ground, smooth Z, shift buildings | ✅ |
| Processing | `cleaning.py` | Clean nodi isolati, condizioni invalide, fill bottom, validate mesh | ✅ |
| Test | `test_meshing.py` | Test triangolazione, settori, refinement sizes, cleaning, terrain | ✅ |

### Fase 3: Edifici ✅ COMPLETATA
**17 test passati (tutti verdi)**

| Modulo | File | Descrizione | Stato |
|--------|------|-------------|-------|
| Processing | `buildings.py` | Posizionamento su terreno, filtro boundary/altezza, distanza da hull | ✅ |
| Test | `test_buildings.py` | Test posizionamento, filtri, distanza, accumulo distanze | ✅ |
| Integrazione | - | Test end-to-end: terreno + edifici → sottrazione → mesh raffinata → export | ❌ DA FARE |

### Fase 4: Geodata + CFD + Pipeline ✅ COMPLETATA
**69 test passati (tutti verdi) — totale progetto: 148 test**

| Modulo | File | Descrizione | Stato |
|--------|------|-------------|-------|
| Geodata | `coordinates.py` | BoundingBox, haversine, latlon↔meters, compute_bbox, pixel size | ✅ |
| Geodata | `dem.py` | Download ASTER GDEM, crop, DEM→MeshPart, DEM→OBJ, merge rasters | ✅ |
| Geodata | `osm.py` | Download edifici OSM, GeoJSON parsing, merge overlapping, extrude 3D | ✅ |
| Test | `test_geodata.py` | 32 test: coordinates, dem, osm (parsing, mesh, OBJ export, merge) | ✅ |
| CFD | `model.py` | CfdModel: assembly modello CFD, fill boundary, assign sectors | ✅ |
| CFD | `boundary.py` | BC dataclass: NoSlip, Slip, Inlet, Outlet + wind direction | ✅ |
| CFD | `parameters.py` | Generazione JSON parametri Kratos FluidDynamicsApplication | ✅ |
| Config | `defaults.py` | Preset: default, urban_wind, terrain_only, osm project | ✅ |
| Test | `test_cfd.py` | 21 test: model, boundary, parameters, defaults | ✅ |
| I/O | `cad_export.py` | Export STEP/IGES via cadquery (opzionale, graceful fallback) | ✅ |
| Pipeline | `runner.py` | Orchestratore pipeline, run_from_json, custom steps | ✅ |
| Pipeline | `steps.py` | 10 step: Load/Preprocess/Domain/Buildings/Subtract/Refine/Clean/CFD/Export | ✅ |
| Test | `test_pipeline.py` | 16 test: steps, runner, integration terrain→export | ✅ |

---

## Mapping Kratos → Python

| Componente Kratos | Sostituzione Python | File |
|---|---|---|
| ModelPart | MeshPart (numpy-backed) | `core/mesh_part.py` |
| SubModelPart | MeshPart.sub_parts dict | `core/mesh_part.py` |
| ExtrusionHeightUtilities (C++) | scipy.spatial.cKDTree O(N log N) | `core/spatial.py` |
| BinBasedFastPointLocator (C++) | scipy.spatial.Delaunay | `core/spatial.py` |
| ComputeNodalGradientProcess3D (C++) | numpy vectorizzato | `core/fields.py` |
| NormalCalculationUtils (C++) | numpy cross product | `core/fields.py` |
| VariationalDistanceProcess | trimesh.proximity + scikit-fmm | `core/fields.py`, `processing/terrain.py` |
| CleaningUtilities (C++) | numpy masks | `processing/cleaning.py` |
| BuildingUtilities (C++) | numpy + trimesh boolean | `processing/importer.py`, `meshing/boolean_ops.py` |
| GeoBuilding.ShiftBuildingOnTerrain | scipy.spatial.Delaunay + barycentric interp | `processing/buildings.py` |
| GeoBuilding.DeleteBuildingsOutsideBoundary | numpy distance filter | `processing/buildings.py` |
| GeoBuilding.DeleteBuildingsUnderValue | numpy Z filter | `processing/buildings.py` |
| GeoBuilding.ComputeDistanceFieldFromHull | trimesh.proximity.signed_distance | `processing/buildings.py` |
| GeoBuilding.AddDistanceFieldFromHull | np.minimum accumulation | `processing/buildings.py` |
| GeoData.DownloadAsterGDEM | requests + NASA CMR API | `geodata/dem.py` |
| GeoData.CropAsterGDEM | rasterio.mask | `geodata/dem.py` |
| GeoData.AsterGDEMtoOBJ | rasterio + numpy tri3 mesh | `geodata/dem.py` |
| GeoData.DownloadBuildingsOSM | requests + Overpass API | `geodata/osm.py` |
| GeoData.GeoJSONtoOBJ | shapely union + triangle lib + extrusion | `geodata/osm.py` |
| GeoData.ComputeBbox | math (haversine formula) | `geodata/coordinates.py` |
| GeoData._measure | haversine (Haversine formula) | `geodata/coordinates.py` |
| GeoModel (assembly CFD) | CfdModel class | `cfd/model.py` |
| FillCfdModelpartUtilities (C++) | CfdModel.fill_parts_fluid/fill_boundary | `cfd/model.py` |
| GeoModel.Inlet_Outlet (settori vento) | CfdModel.assign_inlet_outlet_sectors | `cfd/model.py` |
| GeoModel.NoSlip/Slip/Inlet/Outlet | dataclass BC + parameters.py | `cfd/boundary.py`, `cfd/parameters.py` |
| GeoModel._parameter_initialization | generate_kratos_parameters() | `cfd/parameters.py` |
| MMG/ParMMG raffinamento | gmsh field-based refinement | `meshing/refinement.py` |
| MMG isosurface | trimesh boolean + gmsh re-tet | `meshing/boolean_ops.py` |
| triangle (2D Delaunay) | triangle (mantenuto) | `meshing/triangulation.py` |
| meshpy.tet (TetGen) | meshpy.tet + gmsh | `meshing/domain.py`, `meshing/tetrahedralization.py` |
| Kratos.Parameters (JSON) | Pydantic v2 | `config/settings.py` |
| Kratos.Logger | logging stdlib | tutti i moduli |
| GiD output | trimesh + meshio multi-formato | `io/writers.py` |
| test_application.py (workflow) | PipelineRunner + Steps (Strategy pattern) | `pipeline/runner.py`, `pipeline/steps.py` |

---

## Ambiente

- **Python**: 3.13.12 (C:\Python313\python.exe)
- **Virtual env**: `geodata-processing/.venv/`
- **Dipendenze installate**: numpy, scipy, trimesh, gmsh, meshio, triangle, shapely, rasterio, requests, pydantic, scikit-fmm, pytest, pytest-cov
- **Package installato**: `pip install -e .` (editable mode)

---

## Prossimi Step (in ordine)

1. ~~**Eseguire test Fase 2** (`test_meshing.py`) e fixare eventuali errori~~ ✅
2. ~~**Implementare `processing/buildings.py`** — logica completa import edifici con posizionamento su terreno~~ ✅
3. ~~**Port `geodata/coordinates.py`** — conversioni coordinate geografiche~~ ✅
4. ~~**Port `geodata/dem.py`** — download e processamento dati ASTER GDEM~~ ✅
5. ~~**Port `geodata/osm.py`** — download edifici da OpenStreetMap, merge overlap, extrude 3D~~ ✅
6. ~~**Implementare layer CFD** (`cfd/model.py`, `cfd/boundary.py`, `cfd/parameters.py`)~~ ✅
7. ~~**Implementare `config/defaults.py`** — preset configurazioni (urban_wind, terrain_only, osm)~~ ✅
8. ~~**Implementare `io/cad_export.py`** — export STEP/IGES (opzionale, graceful fallback)~~ ✅
9. ~~**Implementare pipeline** (`pipeline/runner.py`, `pipeline/steps.py`)~~ ✅
10. ~~**Test pipeline** — 16 test: steps, runner, integration terrain→export~~ ✅
11. **Documentazione e cleanup** finale
