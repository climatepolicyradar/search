"""An AWS Python Pulumi program"""

import pulumi
from pulumi_aws import s3

project_name = "search"
bucket = s3.Bucket(project_name)

# Export the name of the bucket
pulumi.export("bucket_name", bucket.id)
