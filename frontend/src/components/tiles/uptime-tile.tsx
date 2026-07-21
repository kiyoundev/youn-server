import { Clock } from "lucide-react";
import { UptimeMeter } from "@/components/ui/uptime-meter";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";

interface UptimeTileProps {
  uptimeSeconds: number;
  className?: string;
}

const UptimeTile = ({ uptimeSeconds, className }: UptimeTileProps) => {
  const days = Math.floor(uptimeSeconds / 86400);
  const hours = Math.floor((uptimeSeconds % 86400) / 3600);

  return (
    <Card className={className ?? "w-fit"}>
      <CardContent className="flex flex-col gap-4 h-full">
        <Clock className="text-brand-200" size={20} strokeWidth={1.25} />
        <div className="flex flex-col gap-1">
          <Label className="text-[22px] font-normal block">
            {days} {days === 1 ? "Day" : "Days"}
          </Label>
          <Label className="text-[14px] font-normal text-brand-300">
            {hours} {hours === 1 ? "Hour" : "Hours"}
          </Label>
        </div>
        <UptimeMeter uptimeSeconds={uptimeSeconds} />
      </CardContent>
    </Card>
  );
};

export default UptimeTile;
