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
│       │   └── cad_export.py       ❌ DA FARE (Fase 4)
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
│       │   └── buildings.py        ❌ DA FARE (Fase 3)
│       ├── geodata/
│       │   ├── dem.py              ❌ DA FARE (Fase 4)
│       │   ├── osm.py              ❌ DA FARE (Fase 4)
│       │   └── coordinates.py      ❌ DA FARE (Fase 4)
│       ├── cfd/
│       │   ├── model.py            ❌ DA FARE (Fase 4)
│       │   ├── boundary.py         ❌ DA FARE (Fase 4)
│       │   └── parameters.py       ❌ DA FARE (Fase 4)
│       ├── config/
│       │   ├── settings.py         ✅ COMPLETATO
│       │   └── defaults.py         ❌ DA FARE (Fase 4)
│       └── pipeline/
│           ├── runner.py           ❌ DA FARE (Fase 4)
│           └── steps.py            ❌ DA FARE (Fase 4)
└── tests/
    ├── test_core.py                ✅ COMPLETATO (17 test)
    ├── test_spatial_fields.py      ✅ COMPLETATO (12 test)
    ├── test_io.py                  ✅ COMPLETATO (4 test)
    ├── test_preprocessing.py       ✅ COMPLETATO (10 test)
    ├── test_config.py              ✅ COMPLETATO (5 test)
    └── test_meshing.py             🔶 SCRITTO, NON ANCORA ESEGUITO
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

### Fase 2: Meshing 🔶 IN CORSO (codice scritto, test da eseguire)

| Modulo | File | Descrizione | Stato |
|--------|------|-------------|-------|
| Meshing | `domain.py` | Dominio cilindrico con terreno, settori vento | ✅ scritto |
| Meshing | `triangulation.py` | Triangolazione 2D (wrapper triangle lib) | ✅ scritto |
| Meshing | `tetrahedralization.py` | Mesh volumetrica (gmsh), da STL, con size field | ✅ scritto |
| Meshing | `refinement.py` | Raffinamento adattivo (gmsh fields), distance-based | ✅ scritto |
| Meshing | `boolean_ops.py` | Sottrazione edifici (trimesh boolean + re-tet) | ✅ scritto |
| Processing | `terrain.py` | Extrusion height, distance from ground, smooth Z, shift buildings | ✅ scritto |
| Processing | `cleaning.py` | Clean nodi isolati, condizioni invalide, fill bottom, validate mesh | ✅ scritto |
| Test | `test_meshing.py` | Test triangolazione, settori, refinement sizes, cleaning, terrain | 🔶 da eseguire |

### Fase 3: Raffinamento + Edifici ❌ DA FARE

| Modulo | File | Descrizione |
|--------|------|-------------|
| Processing | `buildings.py` | Import edifici completo, posizionamento su terreno, distanza da hull |
| Test | `test_buildings.py` | Test import edifici, sottrazione, posizionamento |
| Integrazione | - | Test end-to-end: terreno + edifici → sottrazione → mesh raffinata → export |

### Fase 4: Geodata + CFD + Pipeline ❌ DA FARE

| Modulo | File | Descrizione |
|--------|------|-------------|
| Geodata | `dem.py` | Download ASTER GDEM, crop, conversione a OBJ (port di geo_data.py) |
| Geodata | `osm.py` | Download edifici OpenStreetMap, GeoJSON → OBJ |
| Geodata | `coordinates.py` | Conversione lat/lon ↔ metri, bounding box |
| CFD | `model.py` | Assembly modello CFD (port di geo_model.py) |
| CFD | `boundary.py` | Condizioni al contorno: Inlet, Outlet, Slip, NoSlip |
| CFD | `parameters.py` | Generazione JSON parametri solver |
| I/O | `cad_export.py` | Export STEP/IGES via cadquery (opzionale) |
| Config | `defaults.py` | Valori di default predefiniti |
| Pipeline | `runner.py` | Orchestratore pipeline completo |
| Pipeline | `steps.py` | Step individuali (pattern Strategy) |
| Test | `test_pipeline.py` | Test pipeline end-to-end |

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
| MMG/ParMMG raffinamento | gmsh field-based refinement | `meshing/refinement.py` |
| MMG isosurface | trimesh boolean + gmsh re-tet | `meshing/boolean_ops.py` |
| triangle (2D Delaunay) | triangle (mantenuto) | `meshing/triangulation.py` |
| meshpy.tet (TetGen) | meshpy.tet + gmsh | `meshing/domain.py`, `meshing/tetrahedralization.py` |
| Kratos.Parameters (JSON) | Pydantic v2 | `config/settings.py` |
| Kratos.Logger | logging stdlib | tutti i moduli |
| GiD output | trimesh + meshio multi-formato | `io/writers.py` |

---

## Ambiente

- **Python**: 3.13.12
- **Virtual env**: `geodata-processing/.venv/`
- **Dipendenze installate**: numpy, scipy, trimesh, gmsh, meshio, triangle, shapely, rasterio, requests, pydantic, scikit-fmm, pytest, pytest-cov
- **Package installato**: `pip install -e .` (editable mode)

---

## Prossimi Step (in ordine)

1. **Eseguire test Fase 2** (`test_meshing.py`) e fixare eventuali errori
2. **Implementare `processing/buildings.py`** — logica completa import edifici con posizionamento su terreno
3. **Test integrazione Fase 3** — terreno + edifici → sottrazione → mesh → export
4. **Port `geodata/dem.py`** — download e processamento dati ASTER GDEM
5. **Port `geodata/osm.py`** — download edifici da OpenStreetMap
6. **Port `geodata/coordinates.py`** — conversioni coordinate geografiche
7. **Implementare layer CFD** (`cfd/model.py`, `cfd/boundary.py`, `cfd/parameters.py`)
8. **Implementare `io/cad_export.py`** — export STEP/IGES (opzionale, cadquery)
9. **Implementare pipeline** (`pipeline/runner.py`, `pipeline/steps.py`)
10. **Test end-to-end** — pipeline completo da file input a export multi-formato
11. **Documentazione e cleanup** finale
