"use client";

import { useEffect, useState } from "react";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";

const DateTile = ({ className }: { className?: string }) => {
  const [now, setNow] = useState<Date | null>(null);

  useEffect(() => {
    setNow(new Date());
    const interval = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(interval);
  }, []);

  const time = now
    ? now.toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: true,
      })
    : "";

  const date = now
    ? now.toLocaleDateString("en-US", {
        weekday: "long",
        month: "long",
        day: "numeric",
        year: "numeric",
      })
    : "";

  return (
    <Card className={className ?? "w-fit"}>
      <CardContent className="flex flex-col gap-2">
        <Label className="font-ndot text-[30px] font-normal block">
          {time}
        </Label>
        <Label className="font-ndot text-[18px] font-normal text-brand-300">
          {date}
        </Label>
      </CardContent>
    </Card>
  );
};

export default DateTile;
