import { MemoryStick } from "lucide-react";
import GaugeTile from "@/components/tiles/gauge-tile";

interface MemoryTileProps {
  percent: number;
  totalGb: number;
  className?: string;
}

const MemoryTile = ({ percent, totalGb, className }: MemoryTileProps) => (
  <GaugeTile
    icon={MemoryStick}
    percent={percent}
    gaugeLabel="RAM"
    detail={`${totalGb.toFixed(2)} GB`}
    className={className}
  />
);

export default MemoryTile;
