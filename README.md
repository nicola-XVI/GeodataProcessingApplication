# GeodataProcessingApplication
Application developed for PhD thesis entitled: "Software development for the optimization of the influence of wind flows within energy applications and sustainable town planning"
___

The open-source tool is developed and integrated into the `Kratos Multiphysics` software package (the [GitHub](https://github.com/KratosMultiphysics/Kratos) page). Kratos is designed as an Open-Source framework for the implementation of numerical methods to solve engineering problems. It is written in C++ and designed to allow collaborative development by researchers focusing on modularity and performance.<br><br>

Six separate modules are realized to make the tool as robust as possible, each capable of performing specific operations. In detail, the modules are:
- [`geo_data`](https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/python_scripts/geo_data.py): it allows obtaining the terrain and building geometry data providing only the coordinates of the center and the radius of the domain to be analyzed.
- [`geo_preprocessor`](https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/python_scripts/geo_preprocessor.py): it performs preliminary operations on the data used for realizing the numerical model.
- [`geo_importer`](https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/python_scripts/geo_importer.py): it imports information from different formats such as STL, OBJ, XYZ etc. However, the list can be extended to make the process more versatile.
- [`geo_mesher`](https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/python_scripts/geo_mesher.py): it allows computing the volumetric mesh. For this modulus, two different approaches can be followed. The first method is based on calculating the distance to the terrain surface for performing a metric-based re-mesh procedure. This step can be repeated iteratively to increase the mesh quality. The open-source software [`MMG`](http://www.mmgtools.org/mmg-remesher-try-mmg/mmg-remesher-tutorials/mmg-remesher-mmgs/mmg-remesher-smooth-surface-remeshing) via API in Kratos is used for this purpose. On the other hand, the second approach sets the minimum and maximum dimensions of the contour surface elements.
- [`geo_model`](https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/python_scripts/geo_model.py): it allows both to split the lateral surface of the domain to study different incoming wind directions and create boundary conditions following the conventions in Kratos.

# Dataset
The information for the realization of the numerical model is obtained through two different datasets: one for the terrain and one for the buildings. Both databases are managed by the [`geo_data`](https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/python_scripts/geo_data.py) module.

## Terrain dataset
GDEM (Global Digital Elevation Model) images obtained through the ASTER (Advanced Spaceborne Thermal Emission and Reflection Radiometer) file are used. The ASTER instrumentation is onboard NASA's Terra spacecraft.<br>

A digital elevation model (DEM) is a digital raster representation of ground surface topography or terrain. Each raster cell (or pixel) has a value corresponding to its altitude above sea level.<br>

ASTER-GDEM ([Version 3](https://lpdaac.usgs.gov/products/astgtmv003/)) files are divided into 1-degree by 1-degree data area tiles. The names of the individual data tiles refer to the latitude and longitude at the geometric center of the lower left (southwest) corner pixel. GDEM files can be retrieved through the Earthdata [website](https://search.earthdata.nasa.gov/search/) or [API](https://www.earthdata.nasa.gov/engage/open-data-services-and-software/api/earthdata-search-api).<br>

Figure 1 shows the tile named ASTGTMV003_N42E014, related to the area under evaluation (Pescara).

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_1.png" alt="Figure_1" width="400" align="middle" id="Figure_1">
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
- relation: it is a set of the previous elements. It can be defined as a container used to describe complex objects. For buildings with complex geometry, the relationships are of the Multipolygon type. An example is shown in Figure 2 where the insides polygon represents the interior patio of the building.

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_2.png" alt="Figure_2" width="300" align="middle" id="Figure_2">
  <br>
  <em>Figure 2 - Multipolygon in OSM. way_1: outer perimeter, way_2: inner perimeter</em>
</p>
<br>

Considering the open-source nature of OSM, some areas may be not sufficiently mapped, and, therefore, some buildings are not present. In this case, the buildings can be inserted manually into the OSM through the dedicated section.<br>

Figure 3 shows the area analyzed in this work and the zones in which some buildings are included are highlighted in red.

<p align="center">
  <img src="https://github.com/nicola-XVI/GeodataProcessingApplication/blob/master/images/figure_3.jpg" alt="Figure_3" width="300" align="middle" id="Figure_3">
  <br>
  <em>Figure 3 - Area analyzed in this work: pre-existing buildings (in yellow) and the areas where buildings are added (in red)</em>
</p>
<br>
