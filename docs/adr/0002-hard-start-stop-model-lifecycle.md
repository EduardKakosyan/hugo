# Hard start/stop model lifecycle on the shared DGX Spark

**Status:** accepted

HUGO runs entirely on a DGX Spark (128GB unified memory) that teammates share for their own workloads. We considered keeping a lightweight model server always warm for low-latency starts, but chose to fully load models on HUGO start and fully unload on quit instead, trading cold-start latency (tens of seconds) for guaranteeing teammates get the full memory pool whenever HUGO isn't actively running. This must hold even under crashes/kills, not just clean shutdowns.
