import type { ElementType } from "react";
import type { SvgIconProps } from "@mui/material/SvgIcon";

export function unwrapMuiIcon(iconModule: unknown): ElementType<SvgIconProps> {
  const maybeModule = iconModule as { default?: unknown };
  return (maybeModule.default ?? iconModule) as ElementType<SvgIconProps>;
}
