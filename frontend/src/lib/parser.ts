import { Activity } from "@/types/activity";

function formatPace(speed: number) {
  if (!speed) return "--";

  const paceSeconds = 1000 / speed;

  const min = Math.floor(paceSeconds / 60);
  const sec = Math.round(paceSeconds % 60);

  return `${min}:${sec.toString().padStart(2, "0")}/km`;
}

export function parseActivity(activity: any): Activity {
  return {
    id: activity.id,

    name: activity.name,

    date: activity.start_date_local,

    distanceKm: Number((activity.distance / 1000).toFixed(2)),

    movingTime: activity.moving_time,

    elapsedTime: activity.elapsed_time,

    averageSpeed: activity.average_speed,

    pace: formatPace(activity.average_speed),

    averageHeartRate: activity.average_heartrate ?? null,

    maxHeartRate: activity.max_heartrate ?? null,

    elevation: activity.total_elevation_gain,

    calories: activity.calories ?? 0,

    type: activity.type,
  };
}