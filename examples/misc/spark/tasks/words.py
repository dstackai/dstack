# A trivial Spark app example that counts words occurencies in a text

import os
from operator import add

from pyspark.sql import SparkSession

SPARK_CLUSTER_IP = os.environ["SPARK_CLUSTER_IP"]

# Initialize a Spark session
spark = SparkSession.builder.master(f"spark://{SPARK_CLUSTER_IP}:7077").getOrCreate()

data = [
    "Apache Spark is a unified analytics engine",
    "for large-scale data processing",
    "Spark runs on Hadoop, Apache Mesos, Kubernetes",
    "Standalone, or in the cloud",
    "It can access diverse data sources",
]

# Parallelize the data (create an RDD)
lines = spark.sparkContext.parallelize(data)

# Split each line into words
words = lines.flatMap(lambda line: line.split())

# Map each word to a pair of (word, 1)
word_pairs = words.map(lambda word: (word, 1))

# Reduce by key (word) to count occurrences
word_counts = word_pairs.reduceByKey(add)

# Collect the results and print
results = word_counts.collect()
for word, count in results:
    print(f"{word}: {count}")

# Stop the Spark session
spark.stop()
