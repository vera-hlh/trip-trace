export interface Trip {
  id: number;
  trip_name: string;
  display_name?: string;
  start_date: string;
  end_date: string;
  parent_trip_id: number | null;
  sequence_num?: number;
  location_label?: string;
  file_count?: number;
  sub_trips?: Trip[];
}

export interface MediaFile {
  id: number;
  original_path: string;
  current_path?: string;
  file_name: string;
  file_type: "photo" | "video";
  datetime_original?: string;
  latitude?: number;
  longitude?: number;
  country?: string;
  province?: string;
  city?: string;
  poi?: string;
  has_gps: boolean;
  trip_id?: number;
}
