"""Apply governance/policy.yml to the catalog: grants, PII tags, column masks, row filters.

Runs after every pipeline update, so new tables and columns are governed before
anyone reads them, and grants made by hand outside the policy are revoked.
"""

import argparse
import sys

from pyspark.sql import SparkSession

p = argparse.ArgumentParser()
p.add_argument("--catalog", required=True)
p.add_argument("--src", required=True)
p.add_argument("--policy", required=True)
p.add_argument("--strict", default="false", help="true: fail on missing groups instead of skipping their grants")
args = p.parse_args()

sys.path.append(args.src)

from ucleany import governance  # noqa: E402

spark = SparkSession.builder.getOrCreate()
policy = governance.load_policy(args.policy)
governance.apply(spark, policy, args.catalog, strict=args.strict.lower() == "true")
