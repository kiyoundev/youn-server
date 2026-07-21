import type { LucideIcon } from "lucide-react";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { StatusDot, type ServiceStatus } from "@/components/ui/status-dot";

interface ServiceTileProps {
  icon: LucideIcon;
  name: string;
  status: string;
  healthStatus: ServiceStatus;
  details: string[];
  className?: string;
}

const ServiceTile = ({
  icon: Icon,
  name,
  status,
  healthStatus,
  details,
  className,
}: ServiceTileProps) => {
  return (
    <Card className={className ?? "w-[185px] h-[191.5px] rounded-[12px] bg-muted/50 ring-0"}>
      <CardContent className="flex flex-col gap-4 h-full">
        <Icon className="text-brand-200" size={20} strokeWidth={1.25} />
        <div className="flex flex-col gap-2">
          <Label className="text-[20px] font-normal whitespace-nowrap block">
            {name}
          </Label>
          <div className="flex items-center gap-2">
            <Label className="text-[14px] font-normal text-brand-300 block">
              {status}
            </Label>
            <StatusDot status={healthStatus} />
          </div>
        </div>
        <div className="flex flex-col">
          {details.map((line) => (
            <Label
              key={line}
              className="text-[12px] font-normal text-brand-300"
            >
              {line}
            </Label>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

export default ServiceTile;
