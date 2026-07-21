import type { LucideIcon } from "lucide-react";
import { RadialGauge } from "@/components/ui/radial-gauge";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";

interface GaugeTileProps {
  icon: LucideIcon;
  percent: number;
  gaugeLabel: string;
  detail: string;
  className?: string;
}

const GaugeTile = ({
  icon: Icon,
  percent,
  gaugeLabel,
  detail,
  className,
}: GaugeTileProps) => {
  return (
    <Card className={className ?? "w-fit"}>
      <CardContent className="flex flex-col gap-1">
        <Icon className="text-brand-200" size={20} strokeWidth={1.25} />
        <div className="flex flex-col items-center">
          <RadialGauge percent={percent} label={gaugeLabel} />
          <Label className="text-[12px] font-normal text-brand-300 justify-center -mt-1">
            {detail}
          </Label>
        </div>
      </CardContent>
    </Card>
  );
};

export default GaugeTile;
