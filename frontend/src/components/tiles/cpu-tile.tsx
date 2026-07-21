import { Cpu } from "lucide-react";
import GaugeTile from "@/components/tiles/gauge-tile";

interface CpuTileProps {
  percent: number;
  tempC: number;
  className?: string;
}

const CpuTile = ({ percent, tempC, className }: CpuTileProps) => (
  <GaugeTile
    icon={Cpu}
    percent={percent}
    gaugeLabel="CPU"
    detail={`${tempC.toFixed(2)}°C`}
    className={className}
  />
);

export default CpuTile;
