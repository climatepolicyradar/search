import pulumi

# We're keeping this stack for ease of spinning up new infra, but should consider removing it
pulumi.export("stack", pulumi.get_stack())
