# Clogs
A lightweight toolset to provide visibility into container/stack logs, and their health status.
An alternative to traditional status pages, with deeper insights into your container logs.

Clogs is a stack of tools, consisting of:
- [Clogs Agent](https://github.com/kiliansen/clogs-agent/) - A lightweight service that sources logs/metrics from your containers, and ships them to the Clogs Backend for processing and visualization.
- [Clogs Server](.) - A backend service that receives logs/metrics from the Clogs Agent, processes them, and provides an API for the Clogs Frontend.
- [Clogs Frontend](https://github.com/kiliansen/clogs-frontend) - A web-based dashboard that visualizes the logs/metrics received from the Clogs Backend.

## Deployment Options
Clogs can be deployed in multiple ways, depending on your needs. You can choose to deploy the Clogs Agent standalone, or as part of a compose stack. You can also choose to deploy multiple Clogs Agents, to monitor specific containers only, and ship logs/metrics to a central Clogs Backend.

### Standalone Deployment

#### Integrated Agent
The easiest way to deploy Clogs is to deploy standalone on a host.

By default, an integrated Clogs Agent will monitor all containers on the host, and ship logs/metrics to the Clogs Backend, and visualize them in the Clogs Frontend.

#### Multiple Agents
Alternatively, you can deploy multiple Clogs Agents on the same/different hosts, to monitor specific containers only, and ship logs/metrics to a central Clogs Backend.

#### Only External Agent
You can also deploy only the Clogs Agent externally, to monitor specific containers on a host, and ship logs/metrics to a central Clogs Backend.

### Stack Deployment

#### Integrated Agent
You can also deploy Clogs as part of a compose stack. In this mode, the integrated Clogs Agent can automatically discover other containers in the same stack, and start monitoring their logs/metrics.

#### Multiple Agents
You can deploy multiple Clogs Agents as part of different stacks, to monitor specific containers only, and ship logs/metrics to a central Clogs Backend.

#### Only External Agent
You can also deploy only the Clogs Agent externally, to monitor specific containers in a stack, and ship logs/metrics to a central Clogs Backend.

# Clogs - Server
