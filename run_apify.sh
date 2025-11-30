#!/bin/bash

# Read CSV file and process each username
tail -n +2 data/input-data.csv | while IFS=, read -r name username; do
  # Strip carriage returns (for Windows-style line endings)
  username=$(echo "$username" | tr -d '\r')
  name=$(echo "$name" | tr -d '\r')

  # Skip empty lines
  if [ -z "$username" ]; then
    continue
  fi

  # Get today's date in YYYY-MM-DD format
  today=$(date +"%Y-%m-%d")
  today_compact=$(date +"%Y%m%d")

  # Create data directory structure
  data_dir="data/${today_compact}/linkedin"
  mkdir -p "$data_dir"

  # Check if a file already exists for this username today
  existing_file=$(ls "${data_dir}/dataset_${username}_${today}_"*.json 2>/dev/null | head -n 1)

  if [ -n "$existing_file" ]; then
    echo "Skipping $username - already downloaded today: $existing_file"
    echo ""
    continue
  fi

  # Generate timestamp in the format YYYY-MM-DD_HH-MM-SS-mmm
  timestamp=$(date +"%Y-%m-%d_%H-%M-%S")
  milliseconds=$(( 10#$(date +%N) / 1000000 ))
  full_timestamp="${timestamp}-${milliseconds}"

  # Output filename
  output_file="${data_dir}/dataset_${username}_${full_timestamp}.json"

  echo "Processing username: $username -> $output_file"

  # Run apify command
  echo "{\"username\": \"$username\", \"page_number\": 1, \"limit\": 10}" | apify call apimaestro/linkedin-profile-posts --silent --output-dataset > "$output_file"

  echo "Completed: $output_file"
  echo ""
done

echo "All usernames processed!"
