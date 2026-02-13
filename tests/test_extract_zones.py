from rag.components.vector_store_pipeline import VectorStorePipeline

if __name__ == "__main__":
    pipeline = VectorStorePipeline()
    results = pipeline.query('weather', k=5, agent_role='METEO', zone_id='Dédougou')
    zones = set()
    for chunk in results:
        zone = chunk.get('zone_id')
        if zone:
            zones.add(zone)
        print(f"Chunk: {chunk}\n")
    print(f"\nUnique zones found: {sorted(zones)}")
