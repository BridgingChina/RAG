import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { MapContainer, TileLayer, Marker, useMapEvents } from "react-leaflet"
import L from "leaflet"
import "leaflet/dist/leaflet.css"

// Fix default marker icon paths for bundled builds
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png"
import markerIcon from "leaflet/dist/images/marker-icon.png"
import markerShadow from "leaflet/dist/images/marker-shadow.png"

delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl
L.Icon.Default.mergeOptions({
  iconUrl: markerIcon,
  iconRetinaUrl: markerIcon2x,
  shadowUrl: markerShadow,
})

// Default center: roughly center of China
const DEFAULT_LAT = 31.0
const DEFAULT_LNG = 107.0
const DEFAULT_ZOOM = 5

interface MapCoordinatePickerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialLat?: number | null
  initialLng?: number | null
  onConfirm: (lat: number, lng: number) => void
}

function MapClickHandler({
  onPositionChange,
}: {
  onPositionChange: (lat: number, lng: number) => void
}) {
  useMapEvents({
    click(e) {
      onPositionChange(e.latlng.lat, e.latlng.lng)
    },
  })
  return null
}

export function MapCoordinatePicker({
  open,
  onOpenChange,
  initialLat,
  initialLng,
  onConfirm,
}: MapCoordinatePickerProps) {
  const hasInitial =
    initialLat !== null &&
    initialLat !== undefined &&
    initialLng !== null &&
    initialLng !== undefined

  const [position, setPosition] = useState<{ lat: number; lng: number } | null>(
    hasInitial ? { lat: initialLat!, lng: initialLng! } : null,
  )

  // Reset position when dialog opens with new initial values
  useEffect(() => {
    if (open) {
      if (hasInitial) {
        setPosition({ lat: initialLat!, lng: initialLng! })
      } else {
        setPosition(null)
      }
    }
  }, [open, initialLat, initialLng, hasInitial])

  const center: [number, number] = hasInitial
    ? [initialLat!, initialLng!]
    : [DEFAULT_LAT, DEFAULT_LNG]

  const zoom = hasInitial ? 12 : DEFAULT_ZOOM

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>地图选点</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            点击地图选择桥梁坐标位置
          </p>

          {open && (
            <div className="h-[400px] w-full overflow-hidden rounded-lg border">
              <MapContainer
                center={center}
                zoom={zoom}
                className="h-full w-full"
                scrollWheelZoom={true}
              >
                <TileLayer
                  attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />
                <MapClickHandler
                  onPositionChange={(lat, lng) => setPosition({ lat, lng })}
                />
                {position && (
                  <Marker position={[position.lat, position.lng]} />
                )}
              </MapContainer>
            </div>
          )}

          {position && (
            <p className="text-sm">
              <span className="font-medium">纬度:</span>{" "}
              {position.lat.toFixed(6)}{" "}
              <span className="ml-3 font-medium">经度:</span>{" "}
              {position.lng.toFixed(6)}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            disabled={!position}
            onClick={() => {
              if (position) {
                onConfirm(
                  Number(position.lat.toFixed(6)),
                  Number(position.lng.toFixed(6)),
                )
                onOpenChange(false)
              }
            }}
          >
            确认选点
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
