# GeodataProcessingApplication
Application developed for PhD thesis entitled: "Software development for the optimization of the influence of wind flows within energy applications and sustainable town planning"
___

The open-source tool is developed and integrated into the `Kratos Multiphysics` software package (the [GitHub](https://github.com/KratosMultiphysics/Kratos) page). Kratos is designed as an Open-Source framework for the implementation of numerical methods to solve engineering problems. It is written in C++ and designed to allow collaborative development by researchers focusing on modularity and performance.<br><br>

Six separate modules are realized to make the tool as robust as possible, each capable of performing specific operations. In detail, the modules are:
- [`geo_data`](https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/python_scripts/geo_data.py): it allows obtaining the terrain and building geometry data providing only the coordinates of the center and the radius of the domain to be analyzed.
- [`geo_preprocessor`](https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/python_scripts/geo_preprocessor.py): it performs preliminary operations on the data used for realizing the numerical model.
- [`geo_importer`](https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/python_scripts/geo_importer.py): it imports information from different formats such as STL, OBJ, XYZ etc. However, the list can be extended to make the process more versatile.
- [`geo_mesher`](https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/python_scripts/geo_mesher.py): it allows computing the volumetric mesh. For this modulus, two different approaches can be followed. The first method is based on calculating the distance to the terrain surface for performing a metric-based re-mesh procedure. This step can be repeated iteratively to increase the mesh quality. The open-source software [`MMG`](https://github.com/MmgTools/mmg) via API in Kratos is used for this purpose. On the other hand, the second approach sets the minimum and maximum dimensions of the contour surface elements.
- [`geo_building`](https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/python_scripts/geo_building.py): it performs operations on the building geometry, such as, for example, positioning within the domain and removing buildings outside a given boundary or below a selected elevation.
- [`geo_model`](https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/python_scripts/geo_model.py): it allows both to split the lateral surface of the domain to study different incoming wind directions and create boundary conditions following the conventions in Kratos.

# Dataset
The information for the realization of the numerical model is obtained through two different datasets: one for the terrain and one for the buildings. Both databases are managed by the [`geo_data`](https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/python_scripts/geo_data.py) module.

## Terrain dataset
GDEM (Global Digital Elevation Model) images obtained through the ASTER (Advanced Spaceborne Thermal Emission and Reflection Radiometer) file are used. The ASTER instrumentation is onboard NASA's Terra spacecraft.<br>

A digital elevation model (DEM) is a digital raster representation of ground surface topography or terrain. Each raster cell (or pixel) has a value corresponding to its altitude above sea level.<br>

ASTER-GDEM ([Version 3](https://lpdaac.usgs.gov/products/astgtmv003/)) files are divided into 1-degree by 1-degree data area tiles. The names of the individual data tiles refer to the latitude and longitude at the geometric center of the lower left (southwest) corner pixel. GDEM files can be retrieved through the Earthdata [website](https://search.earthdata.nasa.gov/search/) or [API](https://www.earthdata.nasa.gov/engage/open-data-services-and-software/api/earthdata-search-api).<br>

Figure 1 shows the tile named ASTGTMV003_N42E014, related to the area under evaluation (Pescara).
<br><br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_1.png" alt="Figure_1" width="500" align="middle" id="Figure_1">
  <br>
  <em>Figure 1 - ASTER-GDEM tile of interest area</em>
</p>
<br>

## Building dataset
The geometric model concerning the buildings is obtained through OpenStreetMap (OSM) [website](https://www.openstreetmap.org/#map=6/42.088/12.564) or the [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API). The OSM provides maps of the world with free content. Geographic data in the OSM is under a free license (the Open Database License). This license makes possible the following operations:
- Copy, distribute, use the database,
- Create works from the database,
- Modify, transform, and develop the database.

Each element within the OSM can be represented through four different types:
- node: it indicates both point objects such as trees or traffic lights and, in a simplified way, commercial activities, places of interest etc.,
- way: it is a set of unclosed points and can describe a road, river, path, etc.,
- polygon: it is a closed line and can define a building, lake, park, etc.,
- relation: it is a set of the previous elements. It can be defined as a container used to describe complex objects. For buildings with complex geometry, the relationships are of the Multipolygon type. An example is shown in Figure 2 where the insides polygon represents the interior patio of the building.<br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_2.jpg" alt="Figure_2" width="400" align="middle" id="Figure_2">
  <br>
  <em>Figure 2 - Multipolygon in OSM. way_1: outer perimeter,<br>way_2: inner perimeter</em>
</p>
<br>

Considering the open-source nature of OSM, some areas may be not sufficiently mapped, and, therefore, some buildings are not present. In this case, the buildings can be inserted manually into the OSM through the dedicated section.<br>

Figure 3 shows the area analyzed in this work and the zones in which some buildings are included are highlighted in red.
<br><br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_3.jpg" alt="Figure_3" width="500" align="middle" id="Figure_3">
  <br>
  <em>Figure 3 - Area analyzed in this work: pre-existing buildings (in yellow)<br>and the areas where buildings are added (in red)</em>
</p>
<br>

# Numerical model
The numerical model, generated for performing CFD analyses, is created using information referred to both terrain and building datasets. The operations necessary for the realization of the final numerical model are described in the following subsections.

## Terrain model
Data obtained through the Earthdata portal can be converted into 3D files using the [DEMto3D](https://demto3d.com/) plugin within the [QGIS](https://qgis.org/en/site/) (Quantum Geographic Information System) software. This tool is designed for the conversion of DEM files into 3D printing files.<br>

Tests conducted on small models (with a resolution of a few hundred meters) produce satisfactory results. The tool, however, is strongly limited because it does not allow the conversion of large areas of a few square kilometers useful for realizing numerical models of urban quarters.<br>

For this reason, an automated procedure is created (within the [`geo_data`](https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/python_scripts/geo_data.py) module) for downloading and converting the DEM file into the OBJ format.<br>

After setting the bounding box of the area of interest, the ASTER-GDEM tiles in which the domain falls are downloaded (Figure 4 left) via Earthdata API and the tiles are cut according to the coordinates of the bounding box (Figure 4 right). Subsequently, the DEM file is converted into an OBJ file, thus obtaining a 3D terrain model (Figure 5).
<br><br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_4.jpg" alt="Figure_4" width="500" align="middle" id="Figure_4">
  <br>
  <em>Figure 4 - ASTER-GDEM tile in which the domain falls (left),<br>and the bounding box of the domain (right)</em>
</p>
<br><br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_5.jpg" alt="Figure_5" width="500" align="middle" id="Figure_5">
  <br>
  <em>Figure 5 - 3D model of the terrain</em>
</p>
<br>

A specific condition can appear when the area of interest is situated on several tiles. The worst situation is when it is at the intersection of 4 different tiles (Figure 6). In this case, therefore, it is necessary to merge the tiles and, afterwards, crop the domain of interest.
<br><br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_6.png" alt="Figure_6" width="600" align="middle" id="Figure_6">
  <br>
  <em>Figure 6 - Domain positioned at the intersection of 4 tiles</em>
</p>
<br>

The obtained OBJ file is imported using the [`geo_importer`](https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/python_scripts/geo_importer.py) module.<br>

With the [`geo_preprocessor`](https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/python_scripts/geo_preprocessor.py), however, a circular portion of the terrain surface is cropped and divided into three different areas:
- A central circle with the real orography, where the buildings are placed,
- An intermediate annular portion with only the real orography (without the buildings),
- An outer annular portion, subject to a smoothing procedure, is modeled with a simplified orography with extreme nodes located at zero elevation.

This configuration avoids a discontinuity in the incoming wind speed profile.<br>

The smoothing procedure consists of changing the z-coordinate of the nodes according to the following equation:

$$ z_i = {(z_i - z_{min}) \beta + z_{min}} $$

where $z_i$ is the coordinate of the i-th node, $z_{min}$ is the minimum elevation of the domain, and $\beta$ is a reductive coefficient that can take values between 0.0 and 1.0. It is calculated as:

$$ \beta = 1 - \frac{d_i - r_{ground}}{r_{bondary} - r_{ground}} $$

where $d_i$ is the distance of the i-th node from the center of the domain, $r_{ground}$ is the inner radius of the annular portion with simplified orography, and $r_{boundary}$ is the radius of the domain.<br>

The result of the operations just described is a cloud of points that is converted into a 2D mesh using the [Triangle](https://github.com/drufat/triangle) library (available in Python).<br>

In Figure 7 it is shown the scheme of the points mentioned above.

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_7.png" alt="Figure_7" width="500" align="middle" id="Figure_7">
  <br>
  <em>Figure 7 - Portions of the terrain surface</em>
</p>
<br>

## Buildings model
The [`geo_data`](https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/python_scripts/geo_data.py) module allows, in addition, to download (via the [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API)) and convert the data provided by the OSM into three-dimensional models.<br>

Data via the [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API) are downloaded by providing the bounding box coordinates of the area of interest and the type of data to be extracted. In the specific case, only the information about the buildings is downloaded and stored in a [GeoJSON](https://en.wikipedia.org/wiki/GeoJSON) file.<br>

GeoJSON is an open format that is used to store spatial geometries whose attributes are described through the JavaScript Object Notation. Possible geometries are points, lines, polygons, and multiple collections of these types. The typical structure of a GeoJSON file is like the following:

```json
{
  "type": "way",
  "id": 333362603,
  "bounds": {
    "minlat": 42.4424610,
    "minlon": 14.2067793,
    "maxlat": 42.4429295,
    "maxlon": 14.2073653
  },
  "nodes": [
    3404740665,
    3404740666,
    3404740667,
    3404740668,
    3404740665
  ],
  "geometry": [
    {"lat": 42.4429295, "lon": 14.2072623},
    {"lat": 42.4428541, "lon": 14.2073653},
    {"lat": 42.4424610, "lon": 14.2068823},
    {"lat": 42.4425326, "lon": 14.2067793},
    {"lat": 42.4429295, "lon": 14.2072623}
  ],
  "tags": {
    "building": "apartments",
    "building:levels": "6"
  }
}
```

Information regarding the height of buildings can be provided either as number of floors or as total height. In the first case, the full height is calculated as the product of the number of floors and the storey height, which, by default, is set at 3.0 m.<br>

Within the [`geo_data`](https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/python_scripts/geo_data.py) module, the GeoJSON file is converted into an OBJ format. To do this, first, each building is processed iteratively, and the ground footprint geometry is created; then, it is extruded upwards, obtaining the 3D model. However, this procedure has some limitations:
- tapered buildings are not correctly represented.
- In the case of Multipolygon, only the external perimeter is considered (buildings with internal courtyards are not well modelled).
- Adjacent buildings are combined into a single building, and the joint surface is removed.
- Overlapping buildings are combined into a single building.
- Since the community uploads the information, it may happen that some buildings do not have height information. In this case, a default height is set to create the 3D model of the building.

The result of the procedure just described is shown in Figure 8 and Figure 9.

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_8.png" alt="Figure_8" width="500" align="middle" id="Figure_8">
  <br>
  <em>Figure 8 - 3D model of the buildings obtained through the developed procedure<br>(Top view - city of Pescara)</em>
</p>
<br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_9.png" alt="Figure_9" width="500" align="middle" id="Figure_9">
  <br>
  <em>Figure 9 - 3D model of the buildings obtained through the developed procedure<br>(Axonometric view - city of Pescara)</em>
</p>
<br>

As mentioned in the previous section, the buildings cover only the central portion of the final numerical model. For this reason, a function (in [`geo_building`](https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/python_scripts/geo_building.py) module) is implemented to remove structures outside the given perimeter.<br>

Before merging the geometry of the buildings with one of the terrain, an additional step is necessary to place the buildings at the correct elevation. The OSM, in fact, does not provide the elevation information and, therefore, the buildings are all located on a zero level.<br>

Thanks to the potential provided by Kratos, a function that can calculate the distance (on the z-axis) that each building has with the geometry of the ground is developed within the [`geo_building`](https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/python_scripts/geo_building.py) module. This function allows to shift the building at the exact altitude. The outline of what has just been described is shown below:

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_10.png" alt="Figure_10" width="500" align="middle" id="Figure_10">
  <br>
  <em>Figure 10 - Shifting of buildings on the terrain surface</em>
</p>
<br>

## Final model
The operations described in the previous subsection allow the generation of the 3D model of a portion of a city located anywhere in the world (fully automatically). However, the geometry of the buildings and the terrain are still “separated”, as reported in Figure 11 by using different colours.

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_11.jpg" alt="Figure_11" width="500" align="middle" id="Figure_11">
  <br>
  <em>Figure 11 - Axonometric view of the terrain surface and building geometries</em>
</p>
<br>

Two different procedures are implemented in the [`geo_mesher`](https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/python_scripts/geo_mesher.py) module to obtain the final numerical model.<br>

The first method involves the creation of an initial coarse volumetric mesh in which the geometries of the buildings are inserted. Then, the distance field is calculated with the level-zero on the building's surface through an iterative process. Finally, the refinement process is executed with the [MMG](https://github.com/MmgTools/mmg) library (via API in Kratos).<br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_12.jpg" alt="Figure_12" width="500" align="middle" id="Figure_12">
  <br>
  <em>Figure 12 - Refinement mesh procedure: (a) distance field step 1,<br>(b) distance field step 2, (c) distance field step 3, and (d) result</em>
</p>
<br>

Figure 12 shows a small test carried out on a group of buildings to evaluate the effectiveness of the meshing process. The iterative refinement is performed to improve the quality of the mesh as shown from Figure 12a to Figure 12c. After some iterations, elements with negative distance are removed. The result is a body-fitted mesh (Figure 12d) where smaller elements are placed near the buildings while coarser elements are located away from them.<br>

Good results are also obtained in a complex test case. Figure 13 depicts the result achieved on many buildings with complex shapes. The section on a building (Figure 14) underlines the different sizes of the elements (smaller near the surface of the building and larger away from the building).<br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_13.jpg" alt="Figure_13" width="500" align="middle" id="Figure_13">
  <br>
  <em>Figure 13 - Large scale test with refinement process: axonometric view</em>
</p>
<br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_14.png" alt="Figure_14" width="500" align="middle" id="Figure_14">
  <br>
  <em>Figure 14 - Large scale test with refinement process: section on a building</em>
</p>
<br>

The procedure just described allows to obtain a good quality mesh but with very high computational efforts. This problem can be solved by adopting the parallel version of the used re-mesh tool ([ParMMG](https://github.com/MmgTools/ParMmg)). At the present stage, however, the parallel version is under development. For this reason, a different procedure is created and followed to generate a numerical model by combining terrain and building geometries.<br>

The first step performed with this new procedure involves drilling the terrain surface with the building footprints (Figure 15). This operation allows the creation of new nodes on the terrain surface to insert the geometry of the buildings (Figure 16). Figure 17 shows the terrain surface before and after the "drilling" step focusing on the inserted nodes.<br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_15.jpg" alt="Figure_15" width="600" align="middle" id="Figure_15">
  <br>
  <em>Figure 15 - Terrain surface with the building footprints</em>
</p>
<br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_16.jpg" alt="Figure_16" width="600" align="middle" id="Figure_16">
  <br>
  <em>Figure 16 - Terrain surface with the building geometries</em>
</p>
<br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_17.jpg" alt="Figure_17" width="600" align="middle" id="Figure_17">
  <br>
  <em>Figure 17 - (a) terrain surface before the "drilling" procedure with the new building<br>nodes highlighted, (b) terrain surface after the “drilling” procedure</em>
</p>
<br>

The next step is the creation of the lateral and upper surface of the domain. Then, the minimum and maximum dimensions that the elements can reach are set for each surface. This step is schematized in Figure 18.<br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_18.png" alt="Figure_18" width="500" align="middle" id="Figure_18">
  <br>
  <em>Figure 18 - Size of elements for each mesh. In parentheses the default values</em>
</p>
<br>

Subsequently, the tetrahedral mesh is created through TetGen (available with the [MeshPy](https://documen.tician.de/meshpy/) library in Python). Figure 19 reports the final mesh of a test conducted on a few buildings. The domain has a diameter of 2.0 km and a height of 300.0 m.<br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_19.png" alt="Figure_19" width="500" align="middle" id="Figure_19">
  <br>
  <em>Figure 19 - Tetrahedral mesh on a test case: axonometric view</em>
</p>
<br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_20.png" alt="Figure_20" width="500" align="middle" id="Figure_20">
  <br>
  <em>Figure 20 - Tetrahedral mesh on a test case: detail view of buildings</em>
</p>
<br>

As noted in Figure 19 and Figure 20, the element sizes change in different domain regions. It is due to the dimensions previously set.<br>

To obtain the result reported below, it is necessary to provide only the coordinates of the center of the domain (42.442679 latitudes and 14.207077 longitudes), its diameter and height, and the diameter of the portion of the buildings.<br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_21.jpg" alt="Figure_21" width="500" align="middle" id="Figure_21">
  <br>
  <em>Figure 21 - Numerical model generated with the developed application:<br>terrain and building surfaces (top view)</em>
</p>
<br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_22.png" alt="Figure_22" width="500" align="middle" id="Figure_22">
  <br>
  <em>Figure 22 - Numerical model generated with the developed application:<br>boundary surfaces with the top surface in transparency (axonometric view)</em>
</p>
<br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_23.png" alt="Figure_23" width="500" align="middle" id="Figure_23">
  <br>
  <em>Figure 23 - Numerical model generated with the developed application:<br>detail on building surfaces (axonometric view)</em>
</p>
<br>

To create the volumetric mesh, the minimum and maximum dimensions of the elements for each region are set. This information is indicated in the table reported below:

<p align="center">
  <em>Table 1 - Size of regions and meshes</em>
</p>

| ${\color{#128c7e}Region}$ | ${\color{#128c7e}Inner \\ Radius \\ [m]}$ | ${\color{#128c7e}Outer \\ Radius \\ [m]}$ | ${\color{#128c7e}Height \\ [m]}$ | ${\color{#128c7e}Minimum \\ Surface \\ Size \\ [m]}$ | ${\color{#128c7e}Maximum \\ Surface \\ Size \\ [m]}$ |
| :------------: | :--------------: | :--------------: | :--------: | :----------------------: | :----------------------: |
| Buildings      | -                | 500.00           | -          | 3.00                     | 3.00                     |
| Terrain inner  | -                | 1,000.00         | -          | 5.00                     | 5.00                     |
| Terrain middle | 1,000.00         | 2,000.00         | -          | 5.00                     | 10.00                    |
| Terrain outer  | 2,000.00         | 3,000.00         | -          | 10.00                    | 20.00                    |
| Top            | -                | 3,000.00         | -          | 100.00                   | 100.00                   |
| Lateral        | -                | -                | 500.00     | 20.00                    | 100.00                   |

where the _Terrain inner_ is the central circle where the buildings are located, the _Terrain middle_ is the intermediate annular portion without buildings, and the _Terrain outer_ is the outer annular portion subject to the smoothing procedure.<br>

A tetrahedral mesh is generated on the base of the parameters reported in Table 1. The total number of nodes is 1,379,229, the total number of triangles is 635,948, and one of tetrahedra is 7,764,938.<br>

Triangular elements are the outer faces of the tetrahedra positioned on the external surfaces of the domain. On the triangular elements, the boundary conditions are appropriately set.<br>

Figure 24, Figure 25 and Figure 26 depict, respectively, the axonometric view of a portion of the generated model, a zoom on the buildings and a detail on the building mesh. Lastly, a section is shown in Figure 27 where different elements' sizes relative to the buildings' surface can be seen.

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_24.png" alt="Figure_24" width="500" align="middle" id="Figure_24">
  <br>
  <em>Figure 24 - Tetrahedral mesh of the area under study generated with the<br>developed application: axonometric view</em>
</p>
<br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_25.png" alt="Figure_25" width="500" align="middle" id="Figure_25">
  <br>
  <em>Figure 25 - Tetrahedral mesh of the area under study generated with the<br>developed application: axonometric view of the buildings</em>
</p>
<br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_26.png" alt="Figure_26" width="500" align="middle" id="Figure_26">
  <br>
  <em>Figure 26 - Tetrahedral mesh of the area under study generated with the<br>developed application: detailed mesh on the buildings</em>
</p>
<br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_27.png" alt="Figure_27" width="500" align="middle" id="Figure_27">
  <br>
  <em>Figure 27 - Tetrahedral mesh of the area under study generated with the<br>developed application: section on the buildings</em>
</p>
<br>

# Boundary conditions
Before assigning BCs, the lateral surface is divided into several sectors. The default value is 12, but different values can be set.<br>

The BCs are assigned according to the settings reported in Table 2.

<p align="center">
  <em>Table 2 - BCs assigned</em>
</p>

| | ${\color{#128c7e}Buildings}$ | ${\color{#128c7e}Terrain \\ inner}$ | ${\color{#128c7e}Terrain \\ middle}$ | ${\color{#128c7e}Terrain \\ outer}$ | ${\color{#128c7e}Sectors}$ | ${\color{#128c7e}Top}$ |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| ${\color{#128c7e}BC \\ type}$ | Wall<br>No-Slip | Wall<br>No-Slip | Wall<br>No-Slip | Wall<br>No-Slip | Velocity Inlet /<br>Pressure Outlet | Wall Slip |

The definition of the BCs is handled automatically by the [`geo_model`](https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/python_scripts/geo_model.py) module. Once the analysis to be performed is set (wind from North, East, South or West), the lateral surfaces are fixed as Velocity Inlet or Pressure Outlet, respectively.<br>

The building and terrain surfaces are set as _Wall No-Slip_, while the top surface is defined as _Wall Slip_.<br>

All the information about BCs is enclosed in a JSON file. An example is reported below:

```json
"boundary_conditions_process_list": [
	{
		"Parameters": {
			"model_part_name": "FluidModelPart.Buildings"
		},
		"kratos_module": "KratosMultiphysics.FluidDynamicsApplication",
		"process_name": "ApplyNoSlipProcess",
		"python_module": "apply_noslip_process"
	},
	{
		"Parameters": {
			"model_part_name": "FluidModelPart.TopModelPart"
		},
		"kratos_module": "KratosMultiphysics.FluidDynamicsApplication",
		"process_name": "ApplySlipProcess",
		"python_module": "apply_slip_process"
	},
	{
		"Parameters": {
			"model_part_name": "FluidModelPart.BottomModelPart"
		},
		"kratos_module": "KratosMultiphysics.FluidDynamicsApplication",
		"process_name": " ApplyNoSlipProcess",
		"python_module": "apply_noslip_process"
	},
	
	...
]
```

# Results of CFD analysis
The numerical model, obtained with the above-described application, is tested by performing a CFD simulation. In the present analysis, an incoming wind from the North direction is set, and the obtained results are depicted from Figure 28 to Figure 31.<br>

The results show a very similar trend to those obtained with the microscale commercial software. Specifically, in Figure 28, the velocity magnitude result is shown; in Figure 29, the pressure field with streamlines is reported, in Figure 30, the velocity vectors on a longitudinal section on the reference building are depicted, and in Figure 31, the streamlines on the neighborhood under investigation are plotted.<br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_28.jpg" alt="Figure_28" width="600" align="middle" id="Figure_28">
  <br>
  <em>Figure 28 - Top view of velocity magnitudes: incoming wind from North (-y)</em>
</p>
<br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_29.jpg" alt="Figure_29" width="600" align="middle" id="Figure_29">
  <br>
  <em>Figure 29 - Top view of pressure levels and streamlines:<br>incoming wind from North (-y)</em>
</p>
<br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_30.jpg" alt="Figure_30" width="600" align="middle" id="Figure_30">
  <br>
  <em>Figure 30 - Section view of velocity magnitudes on the reference building:<br>incoming wind from North (-y)</em>
</p>
<br>

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_31.jpg" alt="Figure_31" width="600" align="middle" id="Figure_31">
  <br>
  <em>Figure 31 - Axonometric view of streamlines in the urban fabric:<br>incoming wind from North (-y)</em>
</p>
<br>
