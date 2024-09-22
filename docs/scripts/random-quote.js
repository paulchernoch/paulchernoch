
function pseudo_random_index(seed, max){
  const goldenRatio = (1 + Math.sqrt(5)) / 2;
  return Math.floor((goldenRatio - 1) * seed % max);
}

function day_of_year() {
  const currentDate = new Date();
  const startOfYear = new Date(currentDate.getFullYear(), 0, 1);
  const diffInMilliseconds = currentDate - startOfYear;
  const daysPassed = Math.floor(diffInMilliseconds / (1000 * 60 * 60 * 24));
  return daysPassed
}

// Get a random quote using the day of the year as the random seed.
// The quotes dictionary has the Bible reference (Book Chapter:Verse) as key and the text of the verse as value.
// The quote will be capitalized, as required by the puzzle.
function get_quote(quotes) {
  keys = Object.keys(quotes)
  day = day_of_year()
  random_index = pseudo_random_index(day, keys.length)
  if (random_index >= keys.length) {
    random_index = keys.length - 1;
  }
  key = keys[random_index]
  return quotes[key].toUpperCase()
}

// Shuffle a list randomly.
function shuffle(array) {
  for (let i = array.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [array[i], array[j]] = [array[j], array[i]];
  }
  return array;
}

// Create a random code for the single substitution cipher, a dictionary that maps each uppercase letter to a different letter,
function letter_map() {
  // Create a list of uppercase letters
  var lookup = {};
  let alphabet = [];
  for (let i = 65; i <= 90; i++) {
      alphabet.push(String.fromCharCode(i));
  }

  // Shuffle the alphabet list
  let shuffledAlphabet = shuffle(alphabet);

  for (let ch = 65; ch <= 90; ch++) {
    index = ch - 65
    letter = String.fromCharCode(ch)
    lookup[letter] = shuffledAlphabet[index]
  }
  return lookup;
}