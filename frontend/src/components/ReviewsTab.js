import React, { useState, useEffect } from 'react';
import { useLanguage } from '../LanguageContext';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Textarea } from './ui/textarea';
import { Badge } from './ui/badge';
import { Star, MessageSquare, ThumbsUp } from 'lucide-react';
import api from '../api';
import { toast } from 'sonner';

// Inline star display/input
const Stars = ({ value, max = 5, onChange }) => (
  <div className="flex gap-0.5">
    {Array.from({ length: max }, (_, i) => i + 1).map(star => (
      <button
        key={star}
        type="button"
        onClick={onChange ? () => onChange(star) : undefined}
        className={`text-2xl transition-transform ${onChange ? 'hover:scale-110 cursor-pointer' : 'cursor-default'} ${star <= value ? 'text-yellow-400' : 'text-muted-foreground/30'}`}
      >
        ★
      </button>
    ))}
  </div>
);

const REVIEW_TAGS = [
  'Fast response', 'Accurate diagnosis', 'Friendly', 'Professional',
  'Affordable', 'Highly recommended', 'Good medicine quality', 'Fast delivery',
];

// Who can review who
const ALLOWED_TARGETS = {
  Patient: ['Doctor', 'Pharmacy'],
  Doctor: ['Biomedical Engineer'],
  Pharmacy: ['Biomedical Engineer'],
};

const ReviewsTab = ({ user }) => {
  const { t } = useLanguage();
  const [receivedData, setReceivedData] = useState(null);
  const [myReviews, setMyReviews] = useState([]);
  const [reviewTargets, setReviewTargets] = useState([]); // users I can review
  const [activeSection, setActiveSection] = useState('received');
  const [showForm, setShowForm] = useState(null); // target user doc
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState('');
  const [selectedTags, setSelectedTags] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [featuredQuote, setFeaturedQuote] = useState(null);

  const canReview = ALLOWED_TARGETS[user?.user_type]?.length > 0;

  const loadReceived = async () => {
    try {
      const res = await api.get(`/reviews/user/${user.user_id}`);
      setReceivedData(res.data);
      const featured = res.data.reviews?.find(r => r.is_featured_quote);
      setFeaturedQuote(featured || null);
    } catch (e) {
      console.error(e);
    }
  };

  const loadMyReviews = async () => {
    try {
      const res = await api.get('/reviews/me');
      setMyReviews(res.data.reviews || []);
    } catch (e) {
      console.error(e);
    }
  };

  const loadTargets = async () => {
    if (!canReview) return;
    const allowed = ALLOWED_TARGETS[user?.user_type] || [];
    const targets = [];
    // Load from appointments (doctors) + nearby (all roles)
    try {
      const nearbyRes = await api.get('/nearby?user_type=Doctor&latitude=34.5&longitude=69.2&radius_km=10000');
      const nearbyUsers = (nearbyRes.data.results || []).map(r => r.user);
      for (const u of nearbyUsers) {
        if (allowed.includes(u.user_type) && !targets.find(t => t.user_id === u.user_id)) {
          targets.push(u);
        }
      }
    } catch (e) { /* ignore */ }
    // Also load pharmacies
    if (allowed.includes('Pharmacy')) {
      try {
        const pharmRes = await api.get('/pharmacies/all');
        for (const p of pharmRes.data.pharmacies || []) {
          if (!targets.find(t => t.user_id === p.user_id)) targets.push(p);
        }
      } catch (e) { /* ignore */ }
    }
    setReviewTargets(targets.slice(0, 50));
  };

  useEffect(() => {
    loadReceived();
    loadMyReviews();
    loadTargets();
  }, []);

  const toggleTag = (tag) => {
    setSelectedTags(prev =>
      prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]
    );
  };

  const submitReview = async () => {
    if (!showForm) return;
    setSubmitting(true);
    try {
      await api.post('/reviews', {
        reviewee_id: showForm.user_id,
        rating,
        comment: comment || undefined,
        tags: selectedTags,
      });
      toast.success(t('reviewSubmitted'));
      setShowForm(null);
      setRating(5);
      setComment('');
      setSelectedTags([]);
      loadMyReviews();
    } catch (e) {
      toast.error(e.response?.data?.detail || t('error'));
    } finally {
      setSubmitting(false);
    }
  };

  const setFeatured = async (reviewId) => {
    try {
      await api.put(`/reviews/featured-quote/${reviewId}`);
      toast.success(t('featuredSet'));
      loadReceived();
    } catch (e) {
      toast.error(t('error'));
    }
  };

  const clearFeatured = async () => {
    try {
      await api.delete('/reviews/featured-quote');
      toast.success(t('featuredCleared'));
      loadReceived();
    } catch (e) {
      toast.error(t('error'));
    }
  };

  const deleteReview = async (reviewId) => {
    try {
      await api.delete(`/reviews/${reviewId}`);
      toast.success('Deleted');
      loadMyReviews();
    } catch (e) {
      toast.error(t('error'));
    }
  };

  const avgRating = receivedData?.average_rating || 0;
  const totalReviews = receivedData?.total_reviews || 0;

  return (
    <div className="space-y-6">
      {/* My rating summary */}
      <Card className="border-primary/20 bg-gradient-to-br from-primary/5 to-transparent">
        <CardContent className="p-5 flex flex-col sm:flex-row items-center gap-4">
          <div className="text-center">
            <p className="text-5xl font-bold text-primary">{avgRating > 0 ? avgRating.toFixed(1) : '–'}</p>
            <Stars value={Math.round(avgRating)} />
            <p className="text-xs text-muted-foreground mt-1">{totalReviews} {t('totalReviews')}</p>
          </div>
          {receivedData?.tag_counts && Object.keys(receivedData.tag_counts).length > 0 && (
            <div className="flex flex-wrap gap-2">
              {Object.entries(receivedData.tag_counts)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 6)
                .map(([tag, count]) => (
                  <Badge key={tag} variant="secondary" className="text-xs">
                    {tag} ×{count}
                  </Badge>
                ))}
            </div>
          )}
          {featuredQuote && (
            <div className="flex-1 border-l pl-4 text-start italic text-sm text-muted-foreground">
              <p>"{featuredQuote.comment}"</p>
              <p className="text-xs mt-1 text-primary font-medium not-italic">— {featuredQuote.reviewer_name}</p>
              <Button size="sm" variant="ghost" className="mt-1 text-xs h-6 px-2" onClick={clearFeatured}>
                {t('clearFeatured')}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Section tabs */}
      <div className="flex gap-2 flex-wrap">
        <Button
          variant={activeSection === 'received' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setActiveSection('received')}
        >
          <Star className="w-4 h-4 me-1" /> {t('reviewsReceived')} ({totalReviews})
        </Button>
        <Button
          variant={activeSection === 'given' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setActiveSection('given')}
        >
          <MessageSquare className="w-4 h-4 me-1" /> {t('reviewsGiven')} ({myReviews.length})
        </Button>
        {canReview && (
          <Button
            variant={activeSection === 'write' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setActiveSection('write')}
          >
            <ThumbsUp className="w-4 h-4 me-1" /> {t('writeReview')}
          </Button>
        )}
      </div>

      {/* Reviews received */}
      {activeSection === 'received' && (
        <Card>
          <CardHeader>
            <CardTitle className="text-start">{t('reviewsReceived')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {!receivedData?.reviews?.length ? (
              <p className="text-center text-muted-foreground py-8">{t('noReviewsYet')}</p>
            ) : (
              receivedData.reviews.map(r => (
                <div key={r.review_id} className={`border rounded-lg p-3 text-start space-y-1 ${r.is_featured_quote ? 'border-primary/50 bg-primary/5' : ''}`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Stars value={r.rating} />
                      <span className="text-xs text-muted-foreground">{r.reviewer_name}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      {r.is_featured_quote && <Badge className="text-xs bg-primary">Featured</Badge>}
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-6 px-2 text-xs"
                        onClick={() => setFeatured(r.review_id)}
                        title={t('setFeatured')}
                      >
                        ★
                      </Button>
                    </div>
                  </div>
                  {r.comment && <p className="text-sm italic">"{r.comment}"</p>}
                  {r.tags?.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {r.tags.map(tag => <Badge key={tag} variant="outline" className="text-xs">{tag}</Badge>)}
                    </div>
                  )}
                  <p className="text-xs text-muted-foreground">{new Date(r.created_at).toLocaleDateString()}</p>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      )}

      {/* Reviews given */}
      {activeSection === 'given' && (
        <Card>
          <CardHeader>
            <CardTitle className="text-start">{t('reviewsGiven')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {myReviews.length === 0 ? (
              <p className="text-center text-muted-foreground py-8">{t('noReviewsYet')}</p>
            ) : (
              myReviews.map(r => (
                <div key={r.review_id} className="border rounded-lg p-3 text-start space-y-1">
                  <div className="flex items-center justify-between">
                    <div>
                      <Stars value={r.rating} />
                      <p className="text-xs text-muted-foreground">{t('to')}: {r.reviewee_type}</p>
                    </div>
                    <Button size="sm" variant="ghost" onClick={() => deleteReview(r.review_id)} className="text-red-500 h-6 px-2 text-xs">
                      ✕
                    </Button>
                  </div>
                  {r.comment && <p className="text-sm italic">"{r.comment}"</p>}
                  {r.tags?.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {r.tags.map(tag => <Badge key={tag} variant="outline" className="text-xs">{tag}</Badge>)}
                    </div>
                  )}
                  <p className="text-xs text-muted-foreground">{new Date(r.created_at).toLocaleDateString()}</p>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      )}

      {/* Write a review */}
      {activeSection === 'write' && canReview && (
        <div className="space-y-4">
          {showForm ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-start">{t('reviewFor')}: {showForm.name}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <p className="text-sm font-medium mb-2">{t('yourRating')}</p>
                  <Stars value={rating} onChange={setRating} />
                </div>
                <div className="flex flex-wrap gap-2">
                  {REVIEW_TAGS.map(tag => (
                    <Badge
                      key={tag}
                      variant={selectedTags.includes(tag) ? 'default' : 'outline'}
                      className="cursor-pointer text-xs"
                      onClick={() => toggleTag(tag)}
                    >
                      {tag}
                    </Badge>
                  ))}
                </div>
                <Textarea
                  placeholder={t('reviewComment')}
                  value={comment}
                  onChange={e => setComment(e.target.value)}
                  rows={3}
                />
                <div className="flex gap-2">
                  <Button onClick={submitReview} disabled={submitting}>
                    {submitting ? '...' : t('submitReview')}
                  </Button>
                  <Button variant="outline" onClick={() => setShowForm(null)}>{t('cancel')}</Button>
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardHeader>
                <CardTitle className="text-start">{t('writeReview')}</CardTitle>
              </CardHeader>
              <CardContent>
                {reviewTargets.length === 0 ? (
                  <p className="text-center text-muted-foreground py-8">{t('noTargetsToReview')}</p>
                ) : (
                  <div className="space-y-2">
                    {reviewTargets.map(target => (
                      <div key={target.user_id} className="flex items-center justify-between border rounded-lg p-3">
                        <div className="flex items-center gap-3">
                          {target.picture ? (
                            <img src={target.picture} alt={target.name} className="w-9 h-9 rounded-full object-cover" />
                          ) : (
                            <div className="w-9 h-9 rounded-full bg-primary/20 flex items-center justify-center font-bold text-primary text-sm">
                              {target.name?.[0]?.toUpperCase()}
                            </div>
                          )}
                          <div className="text-start">
                            <p className="font-medium text-sm">{target.name}</p>
                            <p className="text-xs text-muted-foreground">{target.user_type}</p>
                            {target.profile_data?.specialty && (
                              <p className="text-xs text-primary">{target.profile_data.specialty}</p>
                            )}
                          </div>
                        </div>
                        <Button
                          size="sm"
                          onClick={() => {
                            setShowForm(target);
                            setRating(5);
                            setComment('');
                            setSelectedTags([]);
                          }}
                        >
                          {t('leaveReview')}
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
};

export default ReviewsTab;
