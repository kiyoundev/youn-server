import { HardDrive } from "lucide-react";
import { Bay, type BayStatus } from "@/components/ui/bay";
import { StorageMeter } from "@/components/ui/storage-meter";
import { Label } from "@/components/ui/label";
import { formatStorage } from "@/lib/format";
import { Card, CardContent } from "@/components/ui/card";

interface StorageTileProps {
  bays: { label: string; status: BayStatus }[];
  available: number;
  used: number;
  reserved: number;
  className?: string;
}

const StorageTile = ({
  bays,
  available,
  used,
  reserved,
  className,
}: StorageTileProps) => {
  const total = available + used + reserved;

  return (
    <Card className={className ?? "w-fit"}>
      <CardContent className="flex flex-col gap-4">
        <HardDrive className="text-brand-200" size={20} strokeWidth={1.25} />
        <div className="flex gap-7">
          <div className="flex gap-1">
            {(bays ?? []).map((bay) => (
              <Bay key={bay.label} label={bay.label} status={bay.status} />
            ))}
          </div>
          <div className="flex flex-col justify-between">
            <Label className="text-[22px] font-normal block">
              {formatStorage(total)}
            </Label>
            <StorageMeter
              available={available}
              used={used}
              reserved={reserved}
            />
            <div className="flex justify-between">
              <div className="flex gap-1 items-baseline">
                <Label className="text-[16px] font-normal">
                  {formatStorage(used)}
                </Label>
                <Label className="text-[12px] font-normal text-brand-500">
                  Used
                </Label>
              </div>
              <div className="flex gap-1 items-baseline">
                <Label className="text-[16px] font-normal">
                  {formatStorage(available)}
                </Label>
                <Label className="text-[12px] font-normal text-brand-500">
                  Available
                </Label>
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default StorageTile;
