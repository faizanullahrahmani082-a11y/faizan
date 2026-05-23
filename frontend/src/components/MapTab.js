import React, { useState, useEffect, useCallback } from 'react';
import { useLanguage } from '../LanguageContext';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Switch } from './ui/switch';
import { Label } from './ui/label';
import { Badge } from './ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { MapPin, Star, BadgeCheck, Stethoscope, DollarSign, Navigation, Search } from 'lucide-react';
import { formatPrice } from '../utils/currency';
import api from '../api';
import { toast } from 'sonner';

// Fix Leaflet default icon
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

const makeIcon = (color) => new L.Icon({
  iconUrl: `https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-${color}.png`,
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41],
});

const icons = {
  green: makeIcon('green'),
  orange: makeIcon('orange'),
  blue: makeIcon('blue'),
  violet: makeIcon('violet'),
};

const RecenterMap = ({ center }) => {
  const map = useMap();
  useEffect(() => { if (center) map.setView(center, 13); }, [center, map]);
  return null;
};

const SPECIALTIES = [
  'All', 'General Medicine', 'Cardiology', 'Dermatology', 'Orthopedics',
  'Pediatrics', 'Gynecology', 'Neurology', 'Ophthalmology', 'ENT',
  'Psychiatry', 'Radiology', 'Surgery', 'Oncology', 'Endocrinology',
  'Gastroenterology', 'Pulmonology', 'Urology',
];

const StarDisplay = ({ value = 0 }) => (
  <span className="text-yellow-500 text-xs">
    {'★'.repeat(Math.round(value))}{'☆'.repeat(5 - Math.round(value))}
    <span className="text-muted-foreground ml-1">{value > 0 ? value.toFixed(1) : ''}</span>
  </span>
);

const MapTab = ({ user }) => {
  const { t } = useLanguage();
  const [activeTab, setActiveTab] = useState('pharmacies');
  const [center, setCenter] = useState([34.5553, 69.2075]); // Kabul default
  const [geoLoading, setGeoLoading] = useState(false);

  // Pharmacies
  const [pharmacies, setPharmacies] = useState([]);
  const [only247, setOnly247] = useState(false);
  const [onlyFeatured, setOnlyFeatured] = useState(false);

  // Doctors
  const [doctors, setDoctors] = useState([]);
  const [specialty, setSpecialty] = useState('All');
  const [maxFee, setMaxFee] = useState('');
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [doctorSearch, setDoctorSearch] = useState('');

  const loadPharmacies = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (only247) params.append('only_24_7', 'true');
      if (onlyFeatured) params.append('only_featured', 'true');
      const res = await api.get(`/pharmacies/all?${params}`);
      setPharmacies(res.data.pharmacies || []);
    } catch (e) { console.error(e); }
  }, [only247, onlyFeatured]);

  const loadDoctors = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (specialty && specialty !== 'All') params.append('specialty', specialty);
      if (maxFee) params.append('max_fee', maxFee);
      if (verifiedOnly) params.append('verified_only', 'true');
      const res = await api.get(`/doctors?${params}`);
      setDoctors(res.data.doctors || []);
    } catch (e) { console.error(e); }
  }, [specialty, maxFee, verifiedOnly]);

  // Auto-center on browser location
  useEffect(() => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => setCenter([pos.coords.latitude, pos.coords.longitude]),
        () => {},
        { timeout: 5000 }
      );
    }
  }, []);

  useEffect(() => { loadPharmacies(); }, [loadPharmacies]);
  useEffect(() => { if (activeTab === 'doctors') loadDoctors(); }, [activeTab, loadDoctors]);

  const updateMyLocation = async () => {
    if (!navigator.geolocation) { toast.error('Geolocation not available'); return; }
    setGeoLoading(true);
    navigator.geolocation.getCurrentPosition(async (pos) => {
      try {
        await api.post('/location', { latitude: pos.coords.latitude, longitude: pos.coords.longitude });
        toast.success(t('locationUpdated'));
        setCenter([pos.coords.latitude, pos.coords.longitude]);
      } catch (e) {
        toast.error(t('error'));
      } finally {
        setGeoLoading(false);
      }
    }, () => { toast.error(t('locationDenied')); setGeoLoading(false); });
  };

  // Filtered doctors list for sidebar
  const filteredDoctors = doctors.filter(d => {
    if (!doctorSearch) return true;
    const q = doctorSearch.toLowerCase();
    return d.name?.toLowerCase().includes(q) ||
      d.profile_data?.specialty?.toLowerCase().includes(q) ||
      d.profile_data?.hospital?.toLowerCase().includes(q);
  });

  return (
    <div className="space-y-4">
      {/* Tab switcher */}
      <div className="flex gap-2">
        <Button
          variant={activeTab === 'pharmacies' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setActiveTab('pharmacies')}
          data-testid="tab-map-pharmacies"
        >
          <MapPin className="w-4 h-4 me-1" /> {t('nearbyPharmacies')}
        </Button>
        <Button
          variant={activeTab === 'doctors' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setActiveTab('doctors')}
          data-testid="tab-map-doctors"
        >
          <Stethoscope className="w-4 h-4 me-1" /> {t('findDoctors')}
        </Button>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <CardTitle className="text-start text-base">
              {activeTab === 'pharmacies' ? t('nearbyPharmacies') : t('findDoctors')}
            </CardTitle>
            <Button size="sm" variant="outline" onClick={updateMyLocation} disabled={geoLoading} data-testid="update-location-btn">
              <Navigation className={`w-4 h-4 me-1 ${geoLoading ? 'animate-pulse' : ''}`} />
              {geoLoading ? t('detectingLocation') : t('useMyLocation')}
            </Button>
          </div>

          {/* Pharmacy filters */}
          {activeTab === 'pharmacies' && (
            <div className="flex flex-wrap gap-4 items-center pt-2">
              <div className="flex items-center gap-2">
                <Switch checked={only247} onCheckedChange={setOnly247} data-testid="filter-24-7" />
                <Label className="text-sm">{t('show24_7')}</Label>
              </div>
              <div className="flex items-center gap-2">
                <Switch checked={onlyFeatured} onCheckedChange={setOnlyFeatured} data-testid="filter-featured" />
                <Label className="text-sm">{t('showFeatured')}</Label>
              </div>
            </div>
          )}

          {/* Doctor filters */}
          {activeTab === 'doctors' && (
            <div className="flex flex-wrap gap-3 items-end pt-2">
              <div className="relative flex-1 min-w-40">
                <Search className="absolute left-2 top-2.5 w-4 h-4 text-muted-foreground" />
                <Input
                  placeholder={t('searchDoctors')}
                  value={doctorSearch}
                  onChange={e => setDoctorSearch(e.target.value)}
                  className="pl-8"
                  data-testid="doctor-search-map"
                />
              </div>
              <Select value={specialty} onValueChange={setSpecialty}>
                <SelectTrigger className="w-48" data-testid="filter-specialty">
                  <SelectValue placeholder={t('filterSpecialty')} />
                </SelectTrigger>
                <SelectContent>
                  {SPECIALTIES.map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                </SelectContent>
              </Select>
              <div className="flex items-center gap-2">
                <Label className="text-sm whitespace-nowrap">{t('maxFee')} ($)</Label>
                <Input
                  type="number"
                  placeholder="∞"
                  value={maxFee}
                  onChange={e => setMaxFee(e.target.value)}
                  className="w-20"
                  data-testid="filter-max-fee"
                />
              </div>
              <div className="flex items-center gap-2">
                <Switch checked={verifiedOnly} onCheckedChange={setVerifiedOnly} data-testid="filter-verified" />
                <Label className="text-sm">{t('verified')}</Label>
              </div>
            </div>
          )}
        </CardHeader>

        <CardContent className="space-y-3 p-3">
          {/* Map */}
          <div className="rounded-lg overflow-hidden border" style={{ height: '420px' }} data-testid="map-container">
            <MapContainer center={center} zoom={13} style={{ height: '100%', width: '100%' }}>
              <RecenterMap center={center} />
              <TileLayer
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              />

              {/* Pharmacy markers */}
              {activeTab === 'pharmacies' && pharmacies.map(p => {
                const coords = p.location?.location?.coordinates;
                if (!coords) return null;
                return (
                  <Marker key={p.user_id} position={[coords[1], coords[0]]} icon={p.profile_data?.is_24_7 ? icons.orange : icons.green}>
                    <Popup>
                      <div className="space-y-1 min-w-40">
                        <div className="font-semibold flex items-center gap-1">
                          {p.profile_data?.business_name || p.name}
                          {p.is_verified && <BadgeCheck className="w-4 h-4 text-primary inline" />}
                        </div>
                        {p.profile_data?.is_24_7 ? (
                          <Badge className="bg-orange-100 text-orange-800 text-xs">{t('open24_7')}</Badge>
                        ) : p.profile_data?.opening_hours ? (
                          <p className="text-xs">{p.profile_data.opening_hours} – {p.profile_data.closing_hours}</p>
                        ) : null}
                        {p.is_featured && <Badge className="bg-yellow-100 text-yellow-800 text-xs"><Star className="w-3 h-3 me-1" />{t('featured')}</Badge>}
                        {p.location?.address && <p className="text-xs text-gray-500">{p.location.address}</p>}
                      </div>
                    </Popup>
                  </Marker>
                );
              })}

              {/* Doctor markers */}
              {activeTab === 'doctors' && filteredDoctors.map(d => {
                const coords = d.location?.location?.coordinates;
                if (!coords) return null;
                const pd = d.profile_data || {};
                return (
                  <Marker key={d.user_id} position={[coords[1], coords[0]]} icon={d.is_verified ? icons.blue : icons.violet}>
                    <Popup>
                      <div className="space-y-1 min-w-48">
                        <div className="font-semibold flex items-center gap-1">
                          {d.name}
                          {d.is_verified && <BadgeCheck className="w-4 h-4 text-primary inline" />}
                        </div>
                        {pd.specialty && <p className="text-xs text-primary font-medium">{pd.specialty}</p>}
                        {pd.hospital && <p className="text-xs text-gray-500">{pd.hospital}</p>}
                        {pd.consultation_fee != null && (
                          <p className="text-xs flex items-center gap-1">
                            <DollarSign className="w-3 h-3" />
                            {formatPrice(pd.consultation_fee, pd.currency)}
                          </p>
                        )}
                        {d.avg_rating > 0 && <StarDisplay value={d.avg_rating} />}
                        {pd.working_hours && <p className="text-xs text-gray-500">{pd.working_hours}</p>}
                        {d.location?.address && <p className="text-xs text-gray-500">{d.location.address}</p>}
                      </div>
                    </Popup>
                  </Marker>
                );
              })}
            </MapContainer>
          </div>

          {/* Legend */}
          <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
            {activeTab === 'pharmacies' && (
              <>
                <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-green-500 inline-block" /> Regular</span>
                <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-orange-500 inline-block" /> {t('open24_7')}</span>
              </>
            )}
            {activeTab === 'doctors' && (
              <>
                <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-blue-500 inline-block" /> {t('verified')}</span>
                <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-purple-500 inline-block" /> Unverified</span>
              </>
            )}
          </div>

          {/* Doctor sidebar list */}
          {activeTab === 'doctors' && (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {filteredDoctors.length === 0 ? (
                <p className="text-center text-muted-foreground py-4 text-sm">{t('noDoctorsFound')}</p>
              ) : filteredDoctors.map(d => {
                const pd = d.profile_data || {};
                return (
                  <div key={d.user_id} className="border rounded-lg p-3 flex items-center justify-between gap-3 hover:bg-muted/30 transition-colors">
                    <div className="flex items-center gap-3 min-w-0">
                      {d.picture ? (
                        <img src={d.picture} alt={d.name} className="w-10 h-10 rounded-full object-cover shrink-0" />
                      ) : (
                        <div className="w-10 h-10 rounded-full bg-primary/20 flex items-center justify-center font-bold text-primary text-sm shrink-0">
                          {d.name?.[0]?.toUpperCase()}
                        </div>
                      )}
                      <div className="min-w-0 text-start">
                        <div className="flex items-center gap-1 flex-wrap">
                          <span className="font-medium text-sm truncate">{d.name}</span>
                          {d.is_verified && <BadgeCheck className="w-3.5 h-3.5 text-primary shrink-0" />}
                        </div>
                        {pd.specialty && <p className="text-xs text-primary truncate">{pd.specialty}</p>}
                        <div className="flex items-center gap-2 text-xs text-muted-foreground flex-wrap">
                          {pd.consultation_fee != null && (
                            <span>{formatPrice(pd.consultation_fee, pd.currency)}</span>
                          )}
                          {d.avg_rating > 0 && <StarDisplay value={d.avg_rating} />}
                          {pd.working_hours && <span>{pd.working_hours}</span>}
                        </div>
                      </div>
                    </div>
                    <Badge variant="outline" className="text-xs shrink-0">
                      {d.location ? '📍' : '—'}
                    </Badge>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default MapTab;
