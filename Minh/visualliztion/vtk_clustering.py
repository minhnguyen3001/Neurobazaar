import vtk

# Create an instance of vtkKMeansStatistics
kmeans = vtk.vtkKMeansStatistics()

# Provide the input data (as vtkTable or similar)
data_table = vtk.vtkTable()

# Create columns for your data points (features)
feature1 = vtk.vtkDoubleArray()
feature1.SetName("Feature1")
feature2 = vtk.vtkDoubleArray()
feature2.SetName("Feature2")

# Fill the columns with data
feature1.InsertNextValue(1.0)
feature1.InsertNextValue(2.0)
feature1.InsertNextValue(1.5)
feature2.InsertNextValue(1.0)
feature2.InsertNextValue(2.5)
feature2.InsertNextValue(1.8)

# Add the data to the table
data_table.AddColumn(feature1)
data_table.AddColumn(feature2)

# Set the input table
kmeans.SetInputData(data_table)

# Specify which columns to use for clustering
kmeans.SetColumnStatus("Feature1", 1)
kmeans.SetColumnStatus("Feature2", 1)
kmeans.RequestSelectedColumns()

# Specify the number of clusters
kmeans.SetDefaultNumberOfClusters(2)

# Perform the clustering
kmeans.Update()

# Retrieve the output
output_data = kmeans.GetOutputDataObject(0)

# Print cluster assignments
print("Cluster Assignments:")
for i in range(data_table.GetNumberOfRows()):
    cluster_id = output_data.GetValueByName(i, "Cluster Id")
    print(f"Point {i} assigned to Cluster {int(cluster_id)}")

# To retrieve cluster centers:
# VTK typically stores the cluster centers as a vtkMultiBlockDataSet in the output.
print("\nCluster Centers:")
cluster_centers = output_data.GetBlock(1)  # Adjust index if needed
if cluster_centers:
    for i in range(cluster_centers.GetNumberOfPoints()):
        print(f"Cluster {i}: {cluster_centers.GetPoint(i)}")
