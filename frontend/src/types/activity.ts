export interface Activity {
  id: number;

  name: string;

  date: string;

  distanceKm: number;

  movingTime: number;

  elapsedTime: number;

  pace: string;

  averageSpeed: number;

  averageHeartRate: number | null;

  maxHeartRate: number | null;

  elevation: number;

  calories: number;

  type: string;
}