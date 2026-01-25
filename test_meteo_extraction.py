from rag.components.vector_store import VectorStoreHandler

if __name__ == "__main__":
    store = VectorStoreHandler()
    meteo_data = store.get_meteo_data()
    print("Extracted Meteo Data:")
    for entry in meteo_data:
        print(entry)
