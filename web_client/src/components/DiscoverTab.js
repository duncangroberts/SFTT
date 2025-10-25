import React, { useState, useEffect } from 'react';
import { db } from '../firebase';
import {
  collection,
  onSnapshot,
  query,
  orderBy,
  where,
  getDocs,
  doc,
  getDoc,
} from 'firebase/firestore';

const STORIES_LIMIT = 20;
const STATUS_LIST_LIMIT = 10;
const THEME_TABLE_COLUMN_COUNT = 4;

function DiscoverTab() {
  const [themes, setThemes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedTheme, setSelectedTheme] = useState(null);
  const [stories, setStories] = useState([]);
  const [storiesLoading, setStoriesLoading] = useState(false);
  const [storiesError, setStoriesError] = useState(null);

  const normaliseStatus = (value) => (typeof value === 'string' ? value.toLowerCase() : '');

  const formatStatus = (value) => {
    const status = normaliseStatus(value);
    if (!status) {
      return 'Stable';
    }
    return status.charAt(0).toUpperCase() + status.slice(1);
  };

  const activeThemes = themes.filter((theme) => {
    const status = normaliseStatus(theme.discussion_score_trend);
    return status !== 'coma' && status !== 'flatlined';
  });
  const flatlinedThemes = themes
    .filter((theme) => normaliseStatus(theme.discussion_score_trend) === 'flatlined')
    .slice(0, STATUS_LIST_LIMIT);
  const comaThemes = themes
    .filter((theme) => normaliseStatus(theme.discussion_score_trend) === 'coma')
    .slice(0, STATUS_LIST_LIMIT);

  useEffect(() => {
    const themesCollection = collection(db, 'themes');
    const themesQuery = query(themesCollection, orderBy('discussion_score', 'desc'));

    const unsubscribe = onSnapshot(
      themesQuery,
      (snapshot) => {
        const themesData = [];
        snapshot.forEach((docSnapshot) => {
          themesData.push({ id: docSnapshot.id, ...docSnapshot.data() });
        });
        setThemes(themesData);
        setLoading(false);
      },
      (error) => {
        console.error('Error fetching themes:', error);
        setLoading(false);
      }
    );

    return () => unsubscribe();
  }, []);

  const resetStories = () => {
    setStories([]);
    setStoriesError(null);
  };

  const handleThemeClick = async (theme) => {
    if (selectedTheme?.id === theme.id) {
      setSelectedTheme(null);
      resetStories();
      return;
    }

    setSelectedTheme(theme);
    await loadStories(theme);
  };

  const loadStories = async (theme) => {
    resetStories();
    setStoriesLoading(true);

    try {
      const inlineStories = getInlineStories(theme);
      const uniqueStories = new Map();

      inlineStories.forEach((story) => {
        if (story && story.id && !uniqueStories.has(story.id)) {
          uniqueStories.set(story.id, story);
        }
      });

      const { idCandidates, nameCandidates } = buildThemeKeys(theme);
      const linkedStoryIds = await fetchStoryIdsFromThemeStories(idCandidates, nameCandidates);

      linkedStoryIds
        .slice(0, STORIES_LIMIT)
        .forEach((storyId) => {
          if (!uniqueStories.has(storyId)) {
            uniqueStories.set(storyId, { id: storyId });
          }
        });

      const fetchedStories = await fetchStoriesByIds(Array.from(uniqueStories.keys()));
      fetchedStories.forEach((story) => {
        if (story && story.id) {
          uniqueStories.set(story.id, story);
        }
      });

      const mergedStories = Array.from(uniqueStories.values())
        .map((story, index) => normaliseStory(story, 'fallback-' + index))
        .filter(Boolean)
        .sort((a, b) => normaliseDate(b.published_at) - normaliseDate(a.published_at));

      if (!mergedStories.length) {
        setStoriesError('No stories linked to this theme yet.');
      }

      setStories(mergedStories);
    } catch (err) {
      console.error('Error loading stories for theme:', err);
      setStoriesError('Unable to load stories for this theme right now.');
    } finally {
      setStoriesLoading(false);
    }
  };

  const fetchStoryIdsFromThemeStories = async (idCandidates, nameCandidates) => {
    const ids = new Set();
    const themeStoriesCollection = collection(db, 'theme_stories');

    const queryValues = async (field, values) => {
      for (const value of values) {
        if (value === null || value === undefined || value === '') {
          continue;
        }
        try {
          const qRef = query(themeStoriesCollection, where(field, '==', value));
          const snapshot = await getDocs(qRef);
          snapshot.forEach((docSnapshot) => {
            const data = docSnapshot.data();
            if (data && data.story_id !== undefined && data.story_id !== null) {
              ids.add(String(data.story_id));
            }
          });
          if (ids.size >= STORIES_LIMIT) {
            break;
          }
        } catch (err) {
          console.warn('theme_stories query failed', field, value, err);
        }
      }
    };

    if (idCandidates.length) {
      await queryValues('theme_id', idCandidates);
    }

    if (!ids.size && nameCandidates.length) {
      await queryValues('theme_name', nameCandidates);
    }

    return Array.from(ids);
  };

  const fetchStoriesByIds = async (ids) => {
    if (!Array.isArray(ids) || !ids.length) {
      return [];
    }

    const storiesCollection = collection(db, 'stories');
    const limitedIds = Array.from(new Set(ids))
      .filter((value) => value !== undefined && value !== null && value !== '')
      .slice(0, STORIES_LIMIT);

    const docs = await Promise.all(
      limitedIds.map(async (storyId) => {
        try {
          const docSnapshot = await getDoc(doc(storiesCollection, String(storyId)));
          if (docSnapshot.exists()) {
            return { id: docSnapshot.id, ...docSnapshot.data() };
          }
          return null;
        } catch (err) {
          console.warn('Failed to fetch story document', storyId, err);
          return null;
        }
      })
    );

    return docs.filter(Boolean);
  };

  const getInlineStories = (theme) => {
    if (!Array.isArray(theme?.stories)) {
      return [];
    }
    const baseId = theme?.id !== undefined && theme?.id !== null
      ? String(theme.id)
      : theme?.theme_id !== undefined && theme?.theme_id !== null
        ? String(theme.theme_id)
        : 'theme';

    return theme.stories
      .map((item, index) => {
        const fallbackId = baseId + '-inline-' + index;
        return normaliseStory(item, fallbackId);
      })
      .filter(Boolean);
  };

  const buildThemeKeys = (theme) => {
    const idCandidates = new Set();
    const nameCandidates = new Set();

    const pushId = (value) => {
      if (value === null || value === undefined || value === '') {
        return;
      }
      idCandidates.add(value);
      const numeric = Number(value);
      if (!Number.isNaN(numeric)) {
        idCandidates.add(numeric);
      }
    };

    pushId(theme?.theme_id);
    pushId(theme?.id);

    if (theme?.theme_name) {
      nameCandidates.add(theme.theme_name);
    }
    if (theme?.name) {
      nameCandidates.add(theme.name);
    }

    return {
      idCandidates: Array.from(idCandidates),
      nameCandidates: Array.from(nameCandidates),
    };
  };

  const normaliseStory = (raw, fallbackId) => {
    if (!raw || (!raw.title && !raw.headline && !raw.name)) {
      return null;
    }
    const idCandidate = raw.id !== undefined && raw.id !== null
      ? raw.id
      : raw.story_id !== undefined && raw.story_id !== null
        ? raw.story_id
        : raw.storyId !== undefined && raw.storyId !== null
          ? raw.storyId
          : fallbackId;

    if (idCandidate === undefined || idCandidate === null || idCandidate === '') {
      return null;
    }

    const id = String(idCandidate);

    return {
      id,
      title: raw.title || raw.headline || raw.name,
      url: raw.url || raw.link || null,
      source: raw.source || raw.publisher || null,
      summary: raw.summary || raw.abstract || raw.description || null,
      published_at: raw.published_at || raw.date || raw.publishedAt || null,
    };
  };

  const normaliseDate = (value) => {
    if (!value) {
      return 0;
    }
    if (typeof value === 'object' && typeof value.toDate === 'function') {
      return value.toDate().getTime();
    }
    if (value && typeof value.seconds === 'number') {
      return value.seconds * 1000;
    }
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? 0 : parsed.getTime();
  };

  const renderStoryDate = (value) => {
    const timestamp = normaliseDate(value);
    if (!timestamp) {
      return null;
    }
    return new Date(timestamp).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const renderThemeTableRows = (themeList) =>
    themeList.map((theme) => (
      <React.Fragment key={theme.id}>
        <tr
          className={selectedTheme?.id === theme.id ? 'selected' : ''}
          onClick={() => handleThemeClick(theme)}
          tabIndex={0}
          role="button"
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              handleThemeClick(theme);
            }
          }}
        >
          <td>{theme.name}</td>
          <td>{theme.discussion_score}</td>
          <td>{theme.sentiment_score ? theme.sentiment_score.toFixed(2) : 'N/A'}</td>
          <td>{formatStatus(theme.discussion_score_trend)}</td>
        </tr>
        {selectedTheme?.id === theme.id && (
          <tr className="theme-stories-row">
            <td colSpan={THEME_TABLE_COLUMN_COUNT}>
              <div className="theme-stories">
                <h3>Stories for {selectedTheme.name}</h3>
                {storiesLoading ? (
                  <p>Loading stories...</p>
                ) : storiesError ? (
                  <p>{storiesError}</p>
                ) : stories.length > 0 ? (
                  <ul className="stories-list">
                    {stories.map((story) => (
                      <li key={story.id}>
                        <div className="story-headline">
                          {story.url ? (
                            <a href={story.url} target="_blank" rel="noreferrer">
                              {story.title}
                            </a>
                          ) : (
                            <span>{story.title}</span>
                          )}
                        </div>
                        <div className="story-meta">
                          {story.source && <span>{story.source}</span>}
                          {renderStoryDate(story.published_at) && <span>{renderStoryDate(story.published_at)}</span>}
                        </div>
                        {story.summary && <p className="story-summary">{story.summary}</p>}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>No stories linked to this theme yet.</p>
                )}
              </div>
            </td>
          </tr>
        )}
      </React.Fragment>
    ));

  return (
    <div className="tab-content">
      <h2>Discovered Themes</h2>
      {loading ? (
        <p>Loading themes...</p>
      ) : (
        <div className="themes-list">
          {activeThemes.length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th>Theme</th>
                  <th>Discussion Score</th>
                  <th>Sentiment</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {renderThemeTableRows(activeThemes)}
              </tbody>
            </table>
          ) : (
            <p>No active themes found in the database.</p>
          )}

          {flatlinedThemes.length > 0 && (
            <div className="themes-subsection">
              <h3>Flatlined Themes</h3>
              <table>
                <thead>
                  <tr>
                    <th>Theme</th>
                    <th>Discussion Score</th>
                    <th>Sentiment</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>{renderThemeTableRows(flatlinedThemes)}</tbody>
              </table>
            </div>
          )}

          {comaThemes.length > 0 && (
            <div className="themes-subsection">
              <h3>Coma Themes</h3>
              <table>
                <thead>
                  <tr>
                    <th>Theme</th>
                    <th>Discussion Score</th>
                    <th>Sentiment</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>{renderThemeTableRows(comaThemes)}</tbody>
              </table>
            </div>
          )}
        </div>
      )}


    </div>
  );
}

export default DiscoverTab;
