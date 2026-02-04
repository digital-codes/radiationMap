import L from "leaflet";
export function createWindTileLayer(options?: L.TileLayerOptions): L.TileLayer {
    return L.tileLayer("/data/raster_tiles/{z}/{y}/{x}.png", {
        minZoom: 1,
        maxZoom: 6,
        tileSize: 256,
        attribution: "Wind tiles derived from ©ecmwf.int data",
        ...options,
    });
}

export const WindTileLayer = createWindTileLayer;

