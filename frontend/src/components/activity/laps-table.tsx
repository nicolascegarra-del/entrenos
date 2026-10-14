import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  formatDistance,
  formatDuration,
  formatNumber,
  formatPace,
  formatSpeedKmh,
} from "@/lib/format";
import type { Lap } from "@/types/api";

export function LapsTable({ laps, pace }: { laps: Lap[]; pace: boolean }) {
  if (laps.length < 2) return null;
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="font-heading text-lg">Vueltas</CardTitle>
      </CardHeader>
      {/* En móvil la tabla hace scroll horizontal dentro de la tarjeta. */}
      <CardContent className="overflow-x-auto px-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">#</TableHead>
              <TableHead className="text-right">Distancia</TableHead>
              <TableHead className="text-right">Tiempo</TableHead>
              <TableHead className="text-right">
                {pace ? "Ritmo" : "Velocidad"}
              </TableHead>
              <TableHead className="text-right">FC media</TableHead>
              <TableHead className="pr-6 text-right">Cadencia</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {laps.map((lap) => (
              <TableRow key={lap.index}>
                <TableCell className="pl-6 font-medium">
                  {lap.index + 1}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatDistance(lap.distance_m)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatDuration(lap.duration_s)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {pace
                    ? formatPace(lap.avg_speed)
                    : formatSpeedKmh(lap.avg_speed)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatNumber(lap.avg_hr)}
                </TableCell>
                <TableCell className="pr-6 text-right tabular-nums">
                  {formatNumber(lap.metrics.avg_cadence)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
