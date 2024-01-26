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
