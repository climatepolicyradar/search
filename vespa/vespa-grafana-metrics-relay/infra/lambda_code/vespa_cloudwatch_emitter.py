# Copyright 2020 Oath Inc. Licensed under the terms of the Apache 2.0 license. See LICENSE in the project root.
import base64
import json
import logging
import os

import boto3
import urllib3
from urllib3.exceptions import HTTPError, TimeoutError

logging.basicConfig(format="%(asctime)s\t%(levelname)s\t%(message)s")
log = logging.getLogger("vespa_cloudwatch_emitter")
log.setLevel(logging.INFO)


class VespaCloudwatchEmitter:
    chunks_sent = 0

    # See: https://docs.vespa.ai/en/reference/operations/metrics/vespa-metric-set.html
    METRICS_ALLOWLIST = {
        "queries.rate",
        "content.proton.documentdb.feeding.commit.operations.rate",
        "content.proton.documentdb.documents.total.last",
        "content.proton.documentdb.documents.total.max",
        "query_latency.95percentile",
        "query_latency.99percentile",
        "query_latency.average",
        "query_latency.count",
        "query_latency.max",
        "query_latency.sum",
        "http.status.2xx",
        "http.status.4xx",
        "http.status.5xx",
        "feed.http-requests",
        "content.proton.documentdb.disk_usage.last",
        "content.proton.documentdb.disk_usage.average",
        "content.proton.resource_usage.disk.average",
        "content.proton.resource_usage.memory.average",
        "cpu",  # note, this one appears to be undocumented
    }

    # Adding a new dimension will increase the cost exponentially.
    # We should only use dimensions with low cardinality to avoid cost-explosions.
    # "CloudWatch treats each unique combination of dimensions as a separate metric, even if the metrics have the same metric name."
    # @see: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch_concepts.html#dimension-combinations
    DIMENSIONS_ALLOWLIST = {
        "applicationId",
        "documenttype",
        # "cluster",
        # "clusterId",
        # "controller-index",
        # "didWork",
        # "hostname",
        # "serviceId",
        # "workId",
        # "zone",
        # "httpMethod",
        # "protocol",
        # "requestType",
        # "statusCode",
        # "serverName",
        # "serverPort",
        # "api",
        # "operation",
        # "status",
        # "node-type",
        # "destination",
        # "embedder",
        # "language",
        # "endpoint",
        # "handler",
        # "handler-name",
        # "chain",
        # "docproc",
        # "rankProfile",
        # "reason",
        # "context",
        # "host",
        # "parentHostname",
        # "field",
        # "flavor",
        # "interface",
        # "loglevel",
        # "service",
        # "mime",
        # "renderer",
        # "mode",
        # "violation",
        # "client-version",
        # "gcName",
        # "source",
        # "threadpool",
        # "vendor",
    }

    def __init__(self):
        # User constants
        self.VESPA_ENDPOINT = os.environ["VESPA_ENDPOINT"]
        self.CLOUDWATCH_NAMESPACE = os.environ["CLOUDWATCH_NAMESPACE"]
        self.KEY_NAME = os.environ["KEY_NAME"]
        self.CERT_NAME = os.environ["CERT_NAME"]
        self.SSM_REGION = os.environ["SSM_REGION"]
        self.METRICS_API = "metrics/v2/values?consumer=" + os.environ.get(
            "CONSUMER", "default"
        )

        # Vespa constants
        self.CHUNK_SIZE = 20

    def run(self):
        self.chunks_sent = 0
        vespa_url = self.VESPA_ENDPOINT + self.METRICS_API
        log.info("Retrieving Vespa metrics from {}".format(vespa_url))
        try:
            metrics_json = self._get_metrics_json(vespa_url)
            log.debug("json: {}".format(metrics_json))
            if "nodes" not in metrics_json:
                log.warning("No 'nodes' in metrics json")
                return
            metric_data = self.all_metric_data_for_response(metrics_json)
            self._emit_metric_data(metric_data)
            log.info("Finished emitting {} metrics chunks".format(self.chunks_sent))
        except TimeoutError as e:
            log.warning("Timed out connecting to Vespa's metrics api: {}".format(e))
        except HTTPError as e:
            log.warning("Could not connect to Vespa's metrics api: {}".format(e))
        except Exception as e:
            log.warning("Unexpected error: {}".format(e))

    def _emit_metric_data(self, metric_data):
        """Emit metric data in chunks of max CHUNK_SIZE metrics each"""
        cloudwatch = boto3.client("cloudwatch")
        log.info(
            "Emitting {} metrics in chunks of max {}".format(
                len(metric_data), self.CHUNK_SIZE
            )
        )
        metric_data_chunks = self.split_list(metric_data, self.CHUNK_SIZE)
        for chunk in metric_data_chunks:
            log.info("Emitting chunk with {} metrics".format(len(chunk)))
            response = self._emit_to_cloudwatch(cloudwatch, chunk)
            self.chunks_sent += 1
            log.info(response)

    def _emit_to_cloudwatch(self, client, metric_data):
        response = client.put_metric_data(
            MetricData=metric_data, Namespace=self.CLOUDWATCH_NAMESPACE
        )
        return response

    def _get_metrics_json(self, url):
        """Send rest request to metrics api and return the response as JSON"""
        log.info("Sending request to {}".format(url))
        cert_key_pair = self._write_cert_key_pair()
        http = self._get_http(cert_key_pair)
        response = http.request("GET", url)
        return json.loads(response.data.decode("utf-8"))

    def _get_http(self, cert):
        return urllib3.PoolManager(
            cert_file=cert[self.CERT_NAME],
            cert_reqs="CERT_REQUIRED",
            key_file=cert[self.KEY_NAME],
            timeout=urllib3.Timeout(connect=5.0, read=240.0),
        )

    def _write_cert_key_pair(self):
        """
        Retrieves application certificate and key stored in SSM parameter store, and writes result to /tmp/
        :return: Dictionary (key: cert/key name, value: cert/key path)
        """
        ssm = boto3.client("ssm", self.SSM_REGION)
        response = ssm.get_parameters(
            Names=[self.CERT_NAME, self.KEY_NAME], WithDecryption=True
        )
        paths = {}
        for parameter in response["Parameters"]:
            parameter_name = parameter["Name"]
            path = "/tmp/" + parameter_name
            parameter_value_decoded = base64.b64decode(parameter["Value"]).decode(
                "utf-8"
            )
            self._write_file(path, parameter_value_decoded)
            paths[parameter_name] = path
        return paths

    def _write_file(self, path, content):
        f = open(path, "w")
        f.write(content)
        f.close()

    def all_metric_data_for_response(self, response_json):
        metric_data = []
        for nodes_elem in response_json["nodes"]:
            # Using dict.get() to avoid exception if non-existent
            log.info("Parsing metrics from node {}".format(nodes_elem.get("hostname")))

            metric_data.extend(self._metric_data_for_node_node(nodes_elem))
            metric_data.extend(self._metric_data_for_node_services(nodes_elem))
        return metric_data

    def _metric_data_for_node_node(self, nodes_elem):
        """
        Returns a list of MetricsData for the 'node' (= node metrics) element
        for a Vespa node (here represented by nodes_elem).
        """
        if "node" not in nodes_elem:
            log.info(
                "No node metrics for node {} (this is expected for self-hosted Vespa).".format(
                    nodes_elem.get("hostname")
                )
            )
            return []
        return self._metric_data_for_service_or_node(nodes_elem["node"])

    def _metric_data_for_node_services(self, nodes_elem):
        """
        Returns a list of MetricsData for all elements in the 'services'
        list for a Vespa node (here represented by nodes_elem).
        """
        if "services" not in nodes_elem:
            log.warning("No services for node {}".format(nodes_elem.get("hostname")))
            return []

        metric_data = []
        for service in nodes_elem["services"]:
            metric_data.extend(self._metric_data_for_service_or_node(service))
        return metric_data

    def _metric_data_for_service_or_node(self, service_or_node):
        """
        Returns a list of MetricsData for all elements in the 'metrics' json
        list of a 'nodes' element's 'node' element or one of the elements
        in a node's 'services' list.
        """
        if "metrics" not in service_or_node:
            return []
        metric_data = []
        for metrics_elem in service_or_node["metrics"]:
            metric_data.extend(self._get_metrics_with_dimensions(metrics_elem))
        return metric_data

    def _get_metrics_with_dimensions(self, metrics_elem):
        """
        Returns a list of MetricsData for one element in a 'metrics' json list.
        """
        if "values" not in metrics_elem:
            return []
        metric_data = []
        dimensions = self._get_dimensions(metrics_elem)
        for name, value in metrics_elem["values"].items():
            if name not in self.METRICS_ALLOWLIST:
                continue
            metric_data.append(
                {
                    "MetricName": name,
                    "Value": value,
                    "Unit": "None",
                    "Dimensions": dimensions,
                }
            )
        return metric_data

    def _get_dimensions(self, metrics):
        dimensions = []
        if "dimensions" in metrics:
            for dim, dim_val in metrics["dimensions"].items():
                if dim not in self.DIMENSIONS_ALLOWLIST:
                    continue
                dimensions.append({"Name": dim, "Value": dim_val})
        return dimensions

    def split_list(self, lst, chunk_size):
        """
        Splits the given list into chunks and returns the result as a list of lists/chunks
        """
        return [lst[i : i + chunk_size] for i in range(0, len(lst), chunk_size)]


def lambda_handler(event, context):
    VespaCloudwatchEmitter().run()
    return {"statusCode": 200, "body": json.dumps("Done.")}


if __name__ == "__main__":
    VespaCloudwatchEmitter().run()
