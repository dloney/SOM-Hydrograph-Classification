import numpy as np
import pandas as pd
import os, math, copy
from minisom import MiniSom
import matplotlib.pyplot as plt
import sklearn
from sklearn.cluster import MeanShift
from som_functions import *


if __name__ == "__main__":

    ### User inputs ###
    # First line of CSV should be column names. First 2 columns of data should be datetime and streamflow values in ft^3/s.
    input_filename = "/Users/dloney/Documents/follum/inland_hazards/SOM-Hydrograph-Classification/data/Boise hydro_extraction_results/MasterBoiseData.csv"

    # Specify the number of units(days) in each sliding window
    number_of_window_days = 7

    # Specify the number of samples taken each day
    sample_freq = 24

    # If user wants to generate metric cluster plots and SOM cell hydrograph plots, set plots to True below
    # Generating plots increases runtime
    plots = True

    # A correction factor for clustering bandwidth - user may need to tweak
    correction = 1.25

    # The y-axis limit for fixed range cluster plots.
    # User will most likely need to adjust based on dataset if fixed range cluster plots are desired
    min_y = 0
    max_y = 7000

    ################################################################################################################################################################################
    ### Preprocessing ###
    # Read the input data. This may need to be adjusted depending on the format of your data
    #data = pd.read_csv(input_filename, index_col=[0])
    data = pd.read_csv(input_filename, index_col=[0], skiprows=19, usecols=[0, 1], parse_dates=True)
    data = data.iloc[851:, 0]

    # If the dataset has negative values, those are changed to NaN's
    data[data < 0] = np.NAN
 
    # Fills in NaNs where possible by linearly interpolating surrounding data
    data.interpolate(method='linear', limit=2, inplace=True)

    # Changes sampling frequency if it isn't already hourly
    data = resample_timeseries(data, sample_freq)
    sample_freq = 24

    # User must enter desired number of days per window as well as sampling frequency of data above
    window_hours = number_of_window_days * sample_freq

    # Makes the data column into an array to be used with the sliding windows function below
    stream_flows = data.values.flatten()

    # Divides data into sliding windows, each containing the desired number of days per window
    stream_flows = np.lib.stride_tricks.sliding_window_view(stream_flows, window_hours)[::sample_freq, :]

    # Creates column names for a correctly sized dataframe
    columns = []
    for i in range(number_of_window_days * sample_freq):
        # Column names are 0 to n
        columns.append(i)

    # Puts streamflow data into the data frame using column names above
    newdf = pd.DataFrame(stream_flows, columns=columns)

    # Identify rows with NaNs by taking a sum of every row that preserves NaNs and adding it as a column to the newdf
    newdf["sums"] = newdf.sum(axis=1, skipna=False)

    ## Adds a start Date/Time column ##

    # Makes two arrays from the datetime objects and doesn't include the time variable in one so that the unique function can be used below
    date_times = np.asarray(data.index)
    unique_check = np.asarray(data.index.date)

    # Sorts through dates and adds unique dates to the start dates array
    unique_dates, indices = np.unique(unique_check, return_index = True)
    start_dates = date_times[indices]

    # Adjusts list of start dates/times to account for the 6 days in the last 7-day window that will never be start dates
    # This makes the start_datetimes list have the same number of entries as the number of windows from the data
    difference = len(start_dates) - len(stream_flows)
    start_dates = np.delete(start_dates, slice(-difference, len(start_dates)))

    # Adds a column of start dates/times to the dataset
    newdf.insert(0, "Start Date", start_dates)

    # Adds a sample frequency column to the df that tells how often samples are taken each day
    freq_column = []
    for i in range (len(newdf)):
        freq_column.append(sample_freq)
    newdf.insert(1, "Samples Per Day", freq_column)
    
    # Goes through the sums column and removes rows with sums that are NaNs
    i = 0
    for entry in newdf["sums"]:
        if math.isnan(entry):
            newdf = newdf.drop(labels=i, axis=0)
        i += 1

    print("Number of hydrographs:", len(newdf))

    ### Creates folders for script file outputs ###
    # Makes an overall path to hold all results
    results_path = os.path.abspath("results")

    # Creates paths for cluster plots, distribution plots, and metric spreadsheets in outputs
    clusters_path = os.path.join(results_path, "Cluster_plots/")
    fixed_clusters_path = os.path.join(results_path, "Fixed_Range_Cluster_Plots/")
    distributions_path = os.path.join(results_path, "Distributions/")
    metrics_path = os.path.join(results_path, 'Cluster_metrics/')

    # If any of the folders above do not exist, they are created
    if not os.path.isdir(results_path):
        os.makedirs(results_path)

    if not os.path.isdir(clusters_path):
        os.makedirs(clusters_path)

    if not os.path.isdir(fixed_clusters_path):
        os.makedirs(fixed_clusters_path)

    if not os.path.isdir(metrics_path):
        os.makedirs(metrics_path)

    ### Calculating Largest Peak Value and Number of Peaks per Hydrograph Prior to the SOM ###
    # creates a dataset without the frequency column for hydrograph analysis
    # allows the script file to be restarted from this cell after adjustments are made instead of re-reading all input data
    data = newdf.iloc[:, 2:len(newdf.columns) - 1]

    # Makes  a list of 0 through the number of hours in each window
    time_hours = range(data.shape[1])

    # Calculates overall mean of all hydrographs by taking mean of all hydrograph means
    overall_mean = np.mean(np.mean(data))

    # Makes input data an array so that it can be iterated through to perform calcs on each hydrograph
    som_input = data.to_numpy()

    # Finds the value of the largest peak and the number of peaks in each hydrograph
    peaks = []
    intersections = []

    # iterates through every hydrograph in the input data
    for timeseries in som_input:
        # Calls the peakVal function
        peak = calculate_peak_value(timeseries)

        # Calculate the individual hydrograph's mean
        timeseries_mean = np.mean(timeseries)

        if timeseries_mean == 0:
            peaks.append(0)

        else:
            # Scales the peak value by the hydrograph mean and the overall mean of all hydrographs and adds to a list of peaks
            scaled_peak = peak / timeseries_mean * overall_mean
            peaks.append(scaled_peak)

        # Adds number of intersections with a percentile line (peaks) to a list by calling numPeaks function
        intersections.append(count_number_of_peaks(timeseries))

    # Finds the maximum number of peaks out of all hydrographs
    max_peaks = max(intersections)

    # Scales the numbers of peaks list by the maximum number of peaks and overall hydrograph mean
    scaled_intersects = intersections / max_peaks*overall_mean

    # Adds columns containing number of peaks and largest peak values (one value for each parameter for each hydrograph) to the input data
    data["Number of Peaks"] = scaled_intersects
    data["Peaks"] = peaks
    som_input = data.to_numpy()

    ### Creates and trains a 25 x 25 som on the input data array ###
    # Creates and trains a 25 x 25 som on the input data array. Sets a random seed so that results are reproducable.
    som = MiniSom(25, 25, som_input.shape[1], random_seed=1)

    # Uses 2500 training iterations, which was determined to be sufficient for reducing difference between iterations
    som.train(som_input, 2500)

    # win_map shows which hydrographs from input data are contained in each bin of the trained SOM
    win_map = som.win_map(som_input, return_indices = True)

    # Makes a copy of win_map to reference later after changing cell names from original win_map
    win_map_copy = copy.copy(win_map)
    print("Number of SOM cells used:", len(win_map))

    # After fitting the SOM, drops the peaks and intersections from the data so that the hydrograph plots aren't skewed
    data = data.drop("Peaks", axis=1)
    data = data.drop("Number of Peaks", axis=1)
    som_input = data.to_numpy()

    # Preserves current key names in a list
    som_cell_indices = list(win_map.keys())

    # Replaces every old key name with numbers from 0 to the number of SOM cells used
    for i in range(len(win_map)):
        old = som_cell_indices[i]
        win_map[i] = win_map.pop(old)

    # Makes a list of entries from the win_map dictionary
    som_assigned_timeseries = list(win_map.items())

    # Sorts the list of entries by how many hydroraphs are contained in each bin, from highest to lowest number
    som_assigned_timeseries.sort(key=lambda x: len(x[1]), reverse=True)

    ### Plotting hydrographs from each SOM cell ###
    # Makes plots of the all hydrographs contained in each bin if user has set to generate plots
    if plots:
        plot_cells(results_path, som_assigned_timeseries, som_input, time_hours, som_cell_indices)
    
    ### Plots hydrographs from each bin along with the overall weight vector of the bin ###
    # Gets weights and distances for each cell in the SOM
    weights = som.get_weights()
    distances = som.distance_map()

    # Makes lists to be filled with volumes, relevant distance (distances from cells that contain hydrographs), intersections and largest peak outputs for each cell
    volumes, relevant_distances, peaks, intersections = calculate_cell_values(results_path, som_assigned_timeseries, som_input, som_cell_indices, weights, time_hours, distances,
                                                                              plots)
 
    ### Mean-Shift Clustering ###
    # Perform the mean shift clustering
    label, volumes_scaled, flat_distances_scaled = calculate_mean_shift_clustering(volumes, relevant_distances, peaks, intersections, correction)

    # Finds the number of clusters
    unique_labels = np.unique(label)
    print("Number of Clusters: ", len(unique_labels))

    # Adds coordinates for SOM cells containing hydrographs to the dataframe
    cellList = []
    for cell, value in som_assigned_timeseries:
        cellList.append(som_cell_indices[cell])

    # Makes a data frame with the input distance data, the cluster assigned to each data point, and the cell index for each point
    data = pd.DataFrame(flat_distances_scaled)
    data["Volume"] = volumes_scaled
    data["Cluster"] = label
    data["Cell Num"] = range(0, len(relevant_distances.flatten()))
    data["Cell Index"] = cellList

    ### Plotting the clusters and generating results ###
    output_summary_spreadsheet(time_hours, plots, distributions_path, unique_labels, data, win_map_copy, weights, number_of_window_days, sample_freq, som_input,
                               min_y, max_y, clusters_path, fixed_clusters_path, metrics_path, results_path)

    ### Print that the analysis is complete ###
    print("Done")
