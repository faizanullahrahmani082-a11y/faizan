import React, { useState, useEffect } from 'react';
import { useLanguage } from '../LanguageContext';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Switch } from './ui/switch';
import { Label } from './ui/label';
import { Badge } from './ui/badge';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { MapPin, Star, BadgeCheck } from 'lucide-react';
import api from '../api';
import { toast } from 'sonner';

// Fix Leaflet default icon
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

// Custom colored icons
const greenIcon = new L.Icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41],
});
const orangeIcon = new L.Icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-orange.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41],
});

const RecenterMap = ({ center }) => {
  const map = useMap();
  useEffect(() => { if (center) map.setView(center, 13); }, [center, map]);
  return null;
};

const MapTab = () => {
  const { t } = useLanguage();
  const [pharmacies, setPharmacies] = useState([]);
  const [only247, setOnly247] = useState(false);
  const [onlyFeatured, setOnlyFeatured] = useState(false);
  const [center, setCenter] = useState([34.5553, 69.2075]); // Kabul, Afghanistan default

  const loadPharmacies = async () => {
    try {
      const params = new URLSearchParams();
      if (only247) params.append('only_24_7', 'true');
      if (onlyFeatured) params.append('only_featured', 'true');
      const res = await api.get(`/pharmacies/all?${params.toString()}`);
      setPharmacies(res.data.pharmacies || []);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => { loadPharmacies(); }, [only247, onlyFeatured]);

  useEffect(() => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => setCenter([pos.coords.latitude, pos.coords.longitude]),
        () => {}, // fallback to default
        { timeout: 5000 }
      );
    }
  }, []);

  const updateMyLocation = async () => {
    if (!navigator.geolocation) {
      toast.error('Geolocation not available');
      return;
    }
    navigator.geolocation.getCurrentPosition(async (pos) => {
      try {
        await api.post('/location', {
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
        });
        toast.success('Location updated');
        setCenter([pos.coords.latitude, pos.coords.longitude]);
      } catch (e) {
        toast.error(t('error'));
      }
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><MapPin className="w-5 h-5" /> {t('nearbyPharmacies')}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-4 items-center">
          <div className="flex items-center gap-2">
            <Switch checked={only247} onCheckedChange={setOnly247} data-testid="filter-24-7" />
            <Label>{t('show24_7')}</Label>
          </div>
          <div className="flex items-center gap-2">
            <Switch checked={onlyFeatured} onCheckedChange={setOnlyFeatured} data-testid="filter-featured" />
            <Label>{t('showFeatured')}</Label>
          </div>
          <Button size="sm" variant="outline" onClick={updateMyLocation} data-testid="update-location-btn">
            <MapPin className="w-4 h-4 me-1" /> Update My Location
          </Button>
        </div>

        <div className="rounded-lg overflow-hidden border" style={{ height: '500px' }} data-testid="map-container">
          <MapContainer center={center} zoom={13} style={{ height: '100%', width: '100%' }}>
            <RecenterMap center={center} />
            <TileLayer
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            />
            {pharmacies.map(p => {
              const coords = p.location?.location?.coordinates;
              if (!coords) return null;
              const is247 = p.profile_data?.is_24_7;
              return (
                <Marker
                  key={p.user_id}
                  position={[coords[1], coords[0]]}
                  icon={is247 ? orangeIcon : greenIcon}
                >
                  <Popup>
                    <div className="space-y-1">
                      <div className="font-semibold flex items-center gap-1">
                        {p.profile_data?.business_name || p.name}
                        {p.is_verified && <BadgeCheck className="w-4 h-4 text-primary inline" />}
                      </div>
                      {is247 ? (
                        <Badge className="bg-orange-100 text-orange-800">{t('open24_7')}</Badge>
                      ) : (
                        p.profile_data?.opening_hours && (
                          <p className="text-xs">{p.profile_data.opening_hours} - {p.profile_data.closing_hours}</p>
                        )
                      )}
                      {p.is_featured && (
                        <Badge className="bg-yellow-100 text-yellow-800"><Star className="w-3 h-3 me-1" />{t('featured')}</Badge>
                      )}
                      {p.location.address && <p className="text-xs">{p.location.address}</p>}
                    </div>
                  </Popup>
                </Marker>
              );
            })}
          </MapContainer>
        </div>

        <div className="flex gap-4 text-sm">
          <div className="flex items-center gap-2"><div className="w-3 h-3 bg-green-500 rounded-full" /> Regular</div>
          <div className="flex items-center gap-2"><div className="w-3 h-3 bg-orange-500 rounded-full" /> {t('open24_7')}</div>
        </div>
      </CardContent>
    </Card>
  );
};

export default MapTab;
