/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import "./index.css";
import { Composition } from "remotion";
import { KnowPilotDemo } from "./Composition";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="KnowPilotDemo"
      component={KnowPilotDemo}
      durationInFrames={225 * 30}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};
